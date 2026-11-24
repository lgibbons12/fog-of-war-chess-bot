"""Small spatial/temporal transformer with policy and bounded value heads."""
import torch
from torch import nn

from .encoding import ACTION_COUNT, PAD, encode


class HistoryTransformer(nn.Module):
    def __init__(self, window=4, width=64, heads=4, layers=2, policy_head="flat", architecture="factorized"):
        super().__init__()
        if window < 1:
            raise ValueError("window must be positive")
        if policy_head not in ("flat", "pair"):
            raise ValueError("policy_head must be flat or pair")
        if architecture not in ("factorized", "spacetime"):
            raise ValueError("Unknown architecture")
        self.config = dict(window=window, width=width, heads=heads, layers=layers,
                           policy_head=policy_head, architecture=architecture)
        self.symbol = nn.Embedding(PAD + 1, width, padding_idx=PAD)
        if architecture == "spacetime":
            self.file = nn.Embedding(8, width)
            self.rank = nn.Embedding(8, width)
        else:
            self.square = nn.Embedding(64, width)
        self.time = nn.Embedding(window, width)
        self.turn = nn.Embedding(2, width)
        self.observer = nn.Embedding(2, width)
        def encoder():
            layer = nn.TransformerEncoderLayer(width, heads, width * 4,
                                               dropout=0.1, batch_first=True)
            return nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        if architecture == "spacetime":
            self.joint = encoder()
        else:
            self.spatial = encoder()
            self.temporal = encoder()
        if policy_head == "flat":
            self.policy = nn.Linear(width, ACTION_COUNT)
        else:
            self.source = nn.Linear(width, width * 5)
            self.destination = nn.Linear(width, width * 5)
            self.source_bias = nn.Linear(width, 5)
            self.destination_bias = nn.Linear(width, 5)
            self.pair_norm = nn.LayerNorm(width)
        self.value = nn.Linear(width, 1)

    def forward(self, tokens, turns, observer, valid):
        batch, frames, _ = tokens.shape
        squares = torch.arange(64, device=tokens.device)
        times = self.time(torch.arange(frames, device=tokens.device))
        if self.config["architecture"] == "spacetime":
            # Conceptual coordinates: (file, rank, relative observation time).
            # Flattening for attention preserves those coordinates in embeddings.
            positions = self.file(squares % 8) + self.rank(squares // 8)
            features = self.symbol(tokens) + positions[None, None] + times[None, :, None]
            features = features + self.turn(turns)[:, :, None] + self.observer(observer)[:, None, None]
            padding = (~valid)[:, :, None].expand(batch, frames, 64).reshape(batch, frames * 64)
            spatial = self.joint(features.reshape(batch, frames * 64, -1),
                                 src_key_padding_mask=padding).reshape(batch, frames, 64, -1)
            x = spatial[:, -1].mean(dim=1)
        else:
            features = self.symbol(tokens) + self.square(squares)[None, None]
            spatial = self.spatial(features.reshape(batch * frames, 64, -1)).reshape(batch, frames, 64, -1)
            x = spatial.mean(dim=2) + times[None]
            x = x + self.turn(turns) + self.observer(observer)[:, None]
            x = self.temporal(x, src_key_padding_mask=~valid)[:, -1]
        # Every supplied observation precedes the current decision. Joint
        # bidirectional attention over that history introduces no future frames.
        if self.config["policy_head"] == "flat":
            policy = self.policy(x)
        else:
            # Preserve square identities. Temporal context conditions every
            # source/destination pair; promotion is the innermost action axis.
            square_features = self.pair_norm(spatial[:, -1] + x[:, None])
            width = self.config["width"]
            source = self.source(square_features).reshape(batch, 64, 5, width)
            destination = self.destination(square_features).reshape(batch, 64, 5, width)
            policy = torch.einsum("bspd,btpd->bstp", source, destination) / width ** 0.5
            policy = policy + self.source_bias(square_features)[:, :, None, :] + self.destination_bias(square_features)[:, None, :, :]
            policy = policy.reshape(batch, ACTION_COUNT)
        return policy, self.value(x).squeeze(-1).tanh()


def batch_inputs(examples, window, device="cpu"):
    encoded = [encode(history, side, window) for history, side in examples]
    return tuple(torch.tensor(items, dtype=dtype, device=device)
                 for items, dtype in zip(zip(*encoded),
                                         (torch.long, torch.long, torch.long, torch.bool)))


def load_model(path):
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    model = HistoryTransformer(**checkpoint["config"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval()


def initialize_from(model, path):
    """Warm start compatible weights, without claiming identical behavior."""
    source = torch.load(path, map_location="cpu", weights_only=True)["state_dict"]
    target = model.state_dict()
    transferred = []
    for key, tensor in target.items():
        source_key = key.replace("joint.", "spatial.") if key.startswith("joint.") and key not in source else key
        if source_key in source and source[source_key].shape == tensor.shape:
            target[key] = source[source_key]
            transferred.append(key)
    if "file.weight" in target and "square.weight" in source:
        square = source["square.weight"].reshape(8, 8, -1)
        if square.shape[-1] == model.config["width"]:
            target["file.weight"] = square.mean(0)
            target["rank.weight"] = square.mean(1) - square.mean((0, 1))
            transferred.extend(["file.weight", "rank.weight"])
    if "time.weight" in source and source["time.weight"].shape[1] == target["time.weight"].shape[1]:
        old = source["time.weight"]
        new = target["time.weight"]
        count = min(len(old), len(new))
        # The latest observation is always the final slot. Preserve embeddings
        # by age, not by left-aligned index, when changing the window.
        new[-count:] = old[-count:]
        if len(new) > len(old):
            extra = len(new) - len(old)
            slope = (old[1] - old[0]) if len(old) > 1 else torch.zeros_like(old[0])
            for index in range(extra):
                # A conservative initialization, not trained knowledge of older
                # time positions. Fine-tuning should learn these new slots.
                new[index] = old[0] - (extra - index) * 0.25 * slope
        target["time.weight"] = new
        if "time.weight" not in transferred:
            transferred.append("time.weight")
    model.load_state_dict(target)
    return transferred
