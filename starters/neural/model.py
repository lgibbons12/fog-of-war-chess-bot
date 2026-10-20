"""Small CPU inference examples; random weights demonstrate plumbing, not strength."""
import argparse
import json
from pathlib import Path

import torch
from torch import nn


class Policy(nn.Module):
    def __init__(self, kind='feedforward'):
        super().__init__()
        self.kind = kind
        self.encoder = nn.Sequential(
            nn.Conv2d(14, 64, 3, padding=1), nn.ReLU(),
            nn.Conv2d(64, 64, 3, padding=1), nn.ReLU(),
            nn.Flatten(), nn.Linear(4096, 256), nn.ReLU())
        if kind == 'recurrent':
            self.memory = nn.GRUCell(256, 256)
        self.policy = nn.Linear(256, 4096)
        self.value = nn.Linear(256, 1)

    def forward(self, observation, hidden=None):
        features = self.encoder(observation)
        if self.kind == 'recurrent':
            features = self.memory(features, hidden)
        return self.policy(features), self.value(features).tanh(), features


def encode(observation):
    planes = torch.zeros(14, 8, 8)
    symbols = 'PNBRQKpnbrqk?-'
    for square, symbol in enumerate(observation):
        planes[symbols.index(symbol), square // 8, square % 8] = 1
    return planes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['feedforward', 'recurrent', 'search'], default='feedforward')
    args = parser.parse_args()
    path = Path('policy.pt')
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(7980)
    if path.exists():
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        model = Policy(checkpoint['kind'])
        model.load_state_dict(checkpoint['state_dict'])
        print('Keeping supplied policy.pt')
    else:
        model = Policy(args.kind)
        torch.save({'kind': args.kind, 'state_dict': model.state_dict()}, path)
        print(f'Created untrained {args.kind} example')
    model.eval()
    inputs = (torch.zeros(1, 14, 8, 8),)
    names = ['observation']
    if model.kind == 'recurrent':
        inputs += (torch.zeros(1, 256),)
        names.append('hidden')
    outputs = ['policy', 'value', 'next_hidden']
    torch.onnx.export(model, inputs, 'policy.onnx', input_names=names,
                      output_names=outputs, opset_version=17, dynamo=False,
                      dynamic_axes={name: {0: 'batch'} for name in names + outputs})
    # Check exported policy/value/recurrent state numerically before accepting
    # the artifact. Exercise the dynamic batch used by bounded search as well.
    import numpy as np
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = 2, 1
    session = ort.InferenceSession('policy.onnx', options, providers=['CPUExecutionProvider'])
    for batch in (1, 8):
        examples = (torch.randn(batch, 14, 8, 8),)
        if model.kind == 'recurrent':
            examples += (torch.randn(batch, 256),)
        with torch.inference_mode():
            expected = model(*examples)
        actual = session.run(None, {name: value.numpy() for name, value in zip(names, examples)})
        for reference, exported in zip(expected, actual):
            np.testing.assert_allclose(reference.numpy(), exported, rtol=1e-4, atol=1e-5)
    metadata = {'kind': model.kind, 'parameters': sum(p.numel() for p in model.parameters())}
    Path('policy.json').write_text(json.dumps(metadata) + '\n')
    print('Exported CPU inference graph:', metadata)


if __name__ == '__main__':
    main()
