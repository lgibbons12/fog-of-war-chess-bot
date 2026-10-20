# C++ bot

`build.sh` compiles `bot.cpp` with C++20. `run.sh` starts the resulting program.

## ONNX Runtime (CPU)

The native ONNX Runtime **1.24.2** SDK is installed at `/opt/onnxruntime` in the
course runtime. To use it,
include `<onnxruntime_cxx_api.h>` and replace the compile command in `build.sh` with:

```bash
g++ -O2 -std=c++20 -Wall -Wextra bot.cpp -o bot \
  -I/opt/onnxruntime/include -L/opt/onnxruntime/lib \
  -Wl,-rpath,/opt/onnxruntime/lib -lonnxruntime
```

Include your `.onnx` model in the ZIP alongside your code. Do not package the SDK
or download dependencies in `build.sh`. The library is available during both
build and play; the rpath above lets the executable find it without environment
variables.

Read the two initial protocol lines, then create and reuse one session:

```cpp
Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "bot");
Ort::SessionOptions options;
options.SetIntraOpNumThreads(2);
options.SetInterOpNumThreads(1);
Ort::Session session(env, "model.onnx", options);
std::cout << "ready" << std::endl;
```

Load the model and finish initialization within the 15-second readiness deadline.
Use `stderr` for diagnostics; `stdout` must contain only protocol messages. Session
inputs and outputs must match your model's names, types and shapes. See the
[official C++ API documentation](https://onnxruntime.ai/docs/get-started/with-cpp.html).
