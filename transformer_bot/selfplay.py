"""On-policy Monte Carlo actor-critic with observation-only action selection.

Search is deliberately excluded from sampling: policy gradients must use the
distribution that actually generated the moves. One optimizer step per fresh
rollout batch, with dropout disabled during both collection and optimization.
"""
import argparse
from collections import Counter
import copy
import hashlib
import math
import json
from pathlib import Path
import random

import torch
from torch.distributions import Categorical

from referee import FowBoard, observation, outcome, position_key, make_frame, fow_moves
from uniform_random import ObservationTracker
from .encoding import action_index
from .model import batch_inputs, load_model


def distribution(logits, legal_indices):
    mask = torch.full_like(logits, float("-inf"))
    for row, indices in enumerate(legal_indices):
        mask[row, indices] = 0
    return Categorical(logits=logits + mask)


def actor_critic_loss(logits, values, actions, rewards, legal_indices, entropy_weight=0.01):
    policy = distribution(logits, legal_indices)
    advantage = rewards - values.detach()
    actor = -(policy.log_prob(actions) * advantage).mean()
    critic = (values - rewards).square().mean()
    return actor + 0.5 * critic - entropy_weight * policy.entropy().mean()


def play_episode(model, opponent, learner_side, rng, max_plies=200, tactics=False):
    """Full board belongs only to the environment; agents get histories/masks."""
    board = FowBoard()
    trackers = {side: ObservationTracker(side) for side in (True, False)}
    histories = {True: [], False: []}
    counts = Counter({position_key(board): 1})
    transitions = []
    replay = {"white": "learner" if learner_side else "opponent",
              "black": "opponent" if learner_side else "learner",
              "frames": [make_frame(board, [0, 0])]}
    from .opponents import Opponent
    specialist = Opponent(not learner_side, opponent, rng.randrange(2**31)) if isinstance(opponent, str) and opponent in ("tactical", "search") else None
    for ply in range(max_plies + 1):
        terminal = outcome(board, counts)
        if terminal:
            result, reason = terminal
            reward = 0.0 if result == "1/2-1/2" else (1.0 if (result == "1-0") == learner_side else -1.0)
            replay.update(result=result, reason=reason, truncated=False)
            return [(h, s, a, legal, reward, acceptable) for h, s, a, legal, acceptable in transitions], replay
        if ply == max_plies:
            # A rollout cutoff is not a chess draw. Do not train fabricated
            # outcome labels from unfinished games.
            replay.update(result="*", reason="Training rollout cutoff", truncated=True)
            return [], replay
        for side in (True, False):
            view = observation(board, side)
            trackers[side].observe(view)
            if specialist is not None and side != learner_side:
                specialist.observe(view)
            histories[side].append((view, board.turn))
            window = max(model.config["window"], opponent.config["window"] if not isinstance(opponent, str) else 1)
            histories[side] = histories[side][-window:]
        side = board.turn
        tracker, history = trackers[side], histories[side]
        legal = tracker.legal_moves()
        agent = model if side == learner_side else opponent
        if isinstance(agent, str):
            if agent in ("tactical", "search"):
                move = specialist.choose(tracker, history, legal)
                specialist.record_move(move)
            elif agent == "random":
                move = rng.choice(legal)
            elif agent == "capture":
                values = dict(p=1, n=3, b=3, r=5, q=9, k=100)
                move = max(legal, key=lambda m: values.get(tracker.current[m.to_square].lower(), 0) + rng.random() * 0.01)
            else:
                raise ValueError("Unknown opponent")
        else:
            indices = [action_index(move) for move in legal]
            with torch.no_grad():
                logits, _ = agent(*batch_inputs([(history, side)], agent.config["window"]))
                action = int(distribution(logits, [indices]).sample()[0])
            move = legal[indices.index(action)]
            if side == learner_side:
                from .tactics import tactical_targets
                acceptable = tactical_targets(tracker)["acceptable"] if tactics else []
                transitions.append((list(history), side, action, indices, acceptable))
        if move not in fow_moves(board):
            raise AssertionError("Observation move generator disagrees with environment")
        tracker.record_move(move)
        board.push(move)
        counts[position_key(board)] += 1
        replay["frames"].append(make_frame(board, [0, 0], move.uci()))


def update(model, optimizer, transitions, batch_size=16, tactical_weight=0.0):
    model.eval()  # Keep exactly the rollout policy, including dropout behavior.
    optimizer.zero_grad()
    total = 0.0
    for offset in range(0, len(transitions), batch_size):
        batch = transitions[offset:offset + batch_size]
        logits, values = model(*batch_inputs([(e[0], e[1]) for e in batch], model.config["window"]))
        loss = actor_critic_loss(logits, values, torch.tensor([e[2] for e in batch]),
                                 torch.tensor([e[4] for e in batch]), [e[3] for e in batch])
        if tactical_weight:
            from .tactics import tactical_loss
            auxiliary = [(e[0], e[1], e[2], e[4], e[3], 0.0, e[5] if len(e) > 5 else []) for e in batch]
            loss = loss + tactical_weight * tactical_loss(logits, auxiliary)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite RL loss")
        weighted = loss * len(batch) / len(transitions)
        weighted.backward()
        total += float(weighted.detach())
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
    optimizer.step()
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New experiment directory")
    parser.add_argument("--opponents", nargs="*", type=Path, default=[])
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--games-per-iteration", type=int, default=8)
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7980)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--fixed-opponents", nargs="+", choices=["random", "capture", "tactical", "search"], default=["random", "capture"])
    parser.add_argument("--stationary-pool", action="store_true", help="Do not add learner snapshots during controlled comparisons")
    parser.add_argument("--tactical-weight", type=float, default=0.0)
    args = parser.parse_args()
    if args.iterations < 1 or args.games_per_iteration < 2 or args.games_per_iteration % 2 or args.max_plies < 1:
        parser.error("Use positive iterations/max-plies and an even games-per-iteration >= 2")
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        parser.error("learning-rate must be finite and positive")
    if not math.isfinite(args.tactical_weight) or args.tactical_weight < 0:
        parser.error("tactical-weight must be finite and nonnegative")
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(2)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    model = load_model(args.initial)
    pool = [(name, name) for name in args.fixed_opponents] + [("initial", copy.deepcopy(model))]
    pool += [(str(p.resolve()), load_model(p)) for p in args.opponents]
    metadata = {"initial": str(args.initial.resolve()),
                "initial_sha256": hashlib.sha256(args.initial.read_bytes()).hexdigest(),
                "opponents": [{"path": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                              for p in args.opponents],
                "seed": args.seed, "iterations": args.iterations,
                "games_per_iteration": args.games_per_iteration, "max_plies": args.max_plies,
                "learning_rate": args.learning_rate, "fixed_opponents": args.fixed_opponents,
                "stationary_pool": args.stationary_pool, "tactical_weight": args.tactical_weight,
                "entropy_weight": 0.01, "gamma": 1.0}
    (args.output / "experiment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    log = []
    for iteration in range(args.iterations):
        transitions, games = [], []
        for game in range(args.games_per_iteration):
            # Same opponent in both colors. Cycle across iterations as well.
            opponent_name, opponent = pool[(iteration * (args.games_per_iteration // 2) + game // 2) % len(pool)]
            steps, replay = play_episode(model, opponent, game % 2 == 0, rng, args.max_plies, args.tactical_weight > 0)
            transitions.extend(steps)
            games.append({"result": replay["result"], "truncated": replay["truncated"],
                          "learner_white": game % 2 == 0, "plies": len(replay["frames"]) - 1,
                          "opponent": opponent_name})
            (args.output / f"iteration-{iteration:03d}-game-{game:03d}.json").write_text(json.dumps(replay) + "\n")
        loss = update(model, optimizer, transitions, tactical_weight=args.tactical_weight) if transitions else None
        entry = {"iteration": iteration, "transitions": len(transitions), "loss": loss, "games": games}
        log.append(entry)
        torch.save({"config": model.config, "state_dict": model.state_dict(), "kind": "actor_critic",
                    "seed": args.seed, "iteration": iteration, "initial": str(args.initial.resolve())},
                   args.output / f"checkpoint-{iteration:03d}.pt")
        if not args.stationary_pool:
            pool.append((f"iteration-{iteration:03d}", copy.deepcopy(model).eval()))
        # Keep fixed opponents plus a bounded pool of recent snapshots.
        fixed_count = len(args.fixed_opponents) + 1 + len(args.opponents)
        if len(pool) > fixed_count + 5:
            del pool[fixed_count]
        (args.output / "metrics.json").write_text(json.dumps(log, indent=2) + "\n")
        print(json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()
