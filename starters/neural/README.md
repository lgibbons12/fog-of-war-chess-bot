# CPU neural starter

Train on your own computer and include `policy.pt` with your source.
`build.sh` preserves supplied weights. If they are missing, it creates
deterministic **untrained** weights so you can test the build and protocol.
The starter includes a move generator and local referee.
The checkpoint is a dictionary containing `kind` and `state_dict` for `Policy`.
Load it with `torch.load(..., map_location='cpu', weights_only=True)`.

The example provides a feedforward CNN, CNN/GRU (`python3 model.py --kind recurrent`),
and policy/value CNN with one-ply search (`--kind search`). Remove the example
checkpoint before generating another architecture. Search evaluates at most 64
hypothetical post-move observations in batches of eight. It uses only the bot's
observations, without reconstructing hidden pieces. The move generator omits
en passant; you can add it by tracking consecutive observations.

Read `fow` and the color/time-control line, initialize, then write `ready`
followed by a newline and flush `stdout` within 15 seconds. No observations
arrive until both bots are ready. Then respond only to clock prompts.
Initialization happens once per game; the model and recurrent state stay in
memory between turns.

The build loads the supplied PyTorch checkpoint (or generates untrained example
weights), exports `policy.onnx`, and writes model metadata to `policy.json`.
The persistent game bot loads that graph using ONNX Runtime's CPU provider,
with two intra-op threads and one inter-op thread. Using ONNX for play avoids
loading PyTorch within the 15-second initialization limit.

For trusted local testing, install CPU PyTorch, ONNX 1.20.1, ONNX Runtime 1.24.2,
and the kit's `requirements.txt`, then run `bash build.sh` in this folder.
The course runtime already includes these libraries. Do not include your local
virtual environment in the ZIP. See the kit's main guide for local referee
commands and the full protocol.
