## Week 1 — 6 March 2026
- Set up the GitHub repository and installed the core Python dependencies.
- Confirmed the Insta360 GO 3S worked as a USB webcam and verified that both camera routes could be detected.
- Started with a browser-first idea, then pivoted to a hybrid architecture: Python backend for gesture processing and browser frontend for visualization/control.

### What Worked
- MediaPipe hand tracking and OpenCV integration were successfully established.
- The webcam and basic hand landmark detection were working on the target hardware.
- The project direction became clearer after switching to a Python-led architecture.

### What Did Not Work
- The initial browser-only approach was not practical for the project.
- Running the wrong Python environment caused dependency issues, especially with `websockets`.
- MediaPipe import/runtime issues appeared early, including the `sounddevice`/PortAudio crash on some setups.

### Progress
- The project moved from concept exploration to a functioning development base.
- A clear split was established between backend processing and frontend display.

## Week 2 — Architecture and Runtime Stabilization
- Built the main Python pipeline around camera capture, gesture detection, and controller output.
- Added the WebSocket path so browser-based clients could receive live gesture data.
- Established the main project structure around `src/`, `config/`, `web/`, and `tools/`.

### What Worked
- The hybrid Python + browser architecture was suitable for the system.
- WebSocket messaging provided a clean route from backend gesture processing to frontend display.
- The core runtime files became organized into separate responsibilities.

### What Did Not Work
- The first web-based prototype path was too heavy and fragile for the intended workflow.
- Some early dependencies and environment assumptions caused startup failures.

### Progress
- The system moved from setup into a real end-to-end pipeline design.
- The project started to resemble the final dissertation implementation rather than a prototype demo.

## Week 3 — Gesture Detection and Control Mapping
- Implemented gesture detection logic for right-hand finger bends and pinch gestures.
- Implemented left-hand control for joystick direction and D-pad navigation.
- Defined the asymmetric control scheme: left hand for continuous movement, right hand for discrete actions.

### What Worked
- Right-hand bend gestures mapped cleanly to face-button actions.
- Right-hand pinches mapped cleanly to shoulder/trigger actions.
- Left-hand bends mapped to D-pad actions and wrist/inter-hand movement drove joystick control.

### What Did Not Work
- The right analog stick remained unmapped because the camera setup could not reliably recover the depth-dependent motion needed for that channel.
- Some early mapping ideas were too broad and had to be narrowed to the stable, observable gestures only.

### Progress
- The control model became stable and defensible for the dissertation.
- The mapping matched the observed strengths of camera-based hand tracking instead of forcing unreliable controls.

## Week 4 — Output, Smoothing, and Calibration
- Added smoothing and neutral handling so motion output would feel stable rather than jittery.
- Tuned the response using EMA smoothing and a dead zone for the controller output layer.
- Kept the system responsive while reducing unintended drift.

### What Worked
- EMA smoothing improved stability without removing responsiveness.
- The dead zone helped prevent accidental drift at rest.
- The controller output layer handled buttons, triggers, and joystick states cleanly.

### What Did Not Work
- Raw gesture values were too noisy on their own.
- Without filtering, small tracking errors caused unwanted movement.

### Progress
- The pipeline became usable as a real controller instead of just a detection demo.
- The project moved from “it detects hands” to “it produces controlled input.”

## Week 5 — Visualisation, Logging, and Evaluation
- Added the visual overlay system for debugging hand landmarks, gestures, and runtime state.
- Built the latency logging and merged-log analysis workflow for dissertation evaluation.
- Generated the figures and summary statistics used to assess real-time responsiveness.

### What Worked
- The overlay helped verify gesture detection and runtime behavior visually.
- Latency logging and merged analysis made the evaluation measurable rather than anecdotal.
- The notebook-based evaluation produced the key dissertation metrics and figures.

### What Did Not Work
- Some merged log exports lost camera provenance, which limited camera-by-camera conclusions.
- One stage-based figure block was skipped because the merged workbook did not expose the expected stage column names.
- Camera-level comparisons were therefore constrained in the final evaluation dataset.

### Progress
- The project reached a stable evaluation state.
- The dissertation evidence now includes both runtime behavior and measured latency results.

## Final Status
- The active implementation uses a Python backend with MediaPipe hand tracking, WebSocket telemetry, and ViGEm controller output.
- The system meets the median latency target, but tail latency spikes remain present.
- The browser frontend is experimental and optional, not the core control path.