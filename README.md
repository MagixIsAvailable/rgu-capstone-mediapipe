# VisionInput — MediaPipe Gesture Controller for Immersive 360° Room

**CM4134 Capstone Project | Robert Gordon University | 2025–26**  
**Student:** Michal Lazovy 
**Supervisor:** Dr John N.A. Brown  
**External Partner:** James Hutton Institute, Aberdeen  

---

## Project Overview

VisionInput is a plug-and-play gesture controller that replaces standard 
PC game controller input in an immersive 360° room environment using 
real-time hand gesture detection.

A USB camera (Insta360 GO 3S) captures the user's hand gestures via 
Google MediaPipe. The wrapper translates detected gestures into 
HID-compatible controller events, which the game receives as if a 
standard controller is connected — no changes to the game required.

---

## Research Questions

- **RQ1:** How can a MediaPipe gesture pipeline be architected as a 
plug-and-play input wrapper replacing PC controller input in a 360° room?
- **RQ2:** What gesture vocabulary best supports 360° navigation with 
acceptable latency and usability?
- **RQ3:** What are the trade-offs of browser vs edge hardware deployment?

---

## Tech Stack

| Layer | Technology |
|---|---|
| Camera | Insta360 GO 3S (USB webcam mode) |
| Vision / ML | Google MediaPipe Hands + Gesture Recognizer |
| Controller emulation | ViGEm Bus Driver (virtual HID controller) |
| Primary integration | Unity Input System — JHI immersive room game |
| Fallback / parallel | MediaPipe JS + A-Frame — tested in Meta Quest 3S |
| Development | VS Code + GitHub Copilot + Python |

---

## Project Structure
```
src/          — core gesture pipeline and wrapper code
docs/         — project log, architecture diagrams, meeting notes
assets/       — diagrams, screenshots, demo footage
```

---

## Key Deadlines

| Milestone | Date |
|---|---|
| Poster submission | 26 March 2026 |
| Final report | 23 April 2026 |
| Degree Show | 30 April 2026 |

---

## Disclaimer

This repository is private and submitted as part of CM4134 Capstone 
Project at Robert Gordon University. 