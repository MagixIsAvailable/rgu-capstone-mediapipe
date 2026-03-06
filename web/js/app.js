// Global function to handle gestures from external sources
window.handleGesture = function(gestureName) {
    if (!gestureName) return;

    // Update UI
    const displayElement = document.getElementById('gesture-display');
    if (displayElement) {
        displayElement.textContent = `Gesture: ${gestureName}`;
        
        // Add a visual flash effect
        displayElement.classList.add('active');
        setTimeout(() => {
            displayElement.classList.remove('active');
        }, 200);
    }

    console.log(`Received gesture: ${gestureName}`);

    // Get camera rig element (we move the rig, not the camera directly, usually better practice)
    // However, for simple rotation, we rotate the rig or the camera?
    // User wants "rotate camera left/right".
    
    // In A-Frame, "camera" usually has look-controls which overwrites rotation.
    // So we might need to rotate the parent rig wrapper for rotation relative to world,
    // or modify the look-controls usage.
    
    // For simple implementation:
    // "forward" / "back": Move the rig in the direction the camera is facing.
    // "left" / "right": Rotate the rig (yaw).

    const rig = document.getElementById('camera-rig');
    const camera = document.getElementById('camera');

    if (!rig || !camera) {
        console.error("Camera or Rig not found!");
        return;
    }

    // Parameters
    const moveDistance = 0.5;
    const rotateAngle = 15; // degrees

    switch (gestureName.toLowerCase()) {
        case 'forward':
            moveRigForward(rig, camera, moveDistance);
            break;
        case 'back':
            moveRigForward(rig, camera, -moveDistance); // Move backward
            break;
        case 'left':
            rotateRig(rig, rotateAngle);
            break;
        case 'right':
            rotateRig(rig, -rotateAngle);
            break;
        case 'select':
            console.log("selected");
            // Optional: Add visual feedback for select
            break;
        default:
            console.warn(`Unknown gesture: ${gestureName}`);
    }
};

function moveRigForward(rig, camera, distance) {
    // Get the camera's world direction
    const direction = new THREE.Vector3();
    camera.object3D.getWorldDirection(direction);
    
    // We only want to move on the X-Z plane (ground plane), usually:
    // If we want full 3D movement, keep Y. For "walking", flatten Y.
    // Let's assume flying movement (3D) is okay, or flatten if it feels weird.
    // For a 360 image viewer, usually you just move the viewpoint.
    // Since it's a 360 image on a sphere, moving physically inside it doesn't change the parallax
    // of the background (skybox is infinite), but it changes the camera position relative to 
    // any 3D objects if added later.
    // However, just translation without objects might no be noticeable against an `a-sky` unless
    // the sky is actually geometry. `a-sky` is usually centered on camera.
    // Wait, if `a-sky` is used, moving the camera DOES NOT change the view of the background
    // because the skybox moves with the camera or is infinitely far away.
    // BUT the requirement says: "move camera forward 0.5 units".
    // I will implement the movement on the rig. 
    // To make movement visible, I should probably add a reference object or grid?
    // The requirements didn't ask for a grid, but without it, moving in an `a-sky` is invisible.
    // I'll stick to the requirement: "move camera". Even if it's invisible against the sky.
    
    // direction is the vector the camera is looking at.
    // Multiply by distance
    direction.multiplyScalar(distance);
    
    // Since we are moving the rig, we take the rig's current position and add the vector
    // But we need to account for rig rotation if the rig itself is rotated?
    // Actually, getWorldDirection gives the absolute direction.
    // So we can just add this vector to the rig's world position.

    rig.object3D.position.add(direction);
}

function rotateRig(rig, degrees) {
    // Rotate around Y axis
    const rad = THREE.MathUtils.degToRad(degrees);
    rig.object3D.rotation.y += rad;
}

// For testing purposes, we can listen to keyboard events to simulate gestures
document.addEventListener('keydown', (event) => {
    switch(event.key) {
        case 'ArrowUp':
            window.handleGesture('forward');
            break;
        case 'ArrowDown':
            window.handleGesture('back');
            break;
        case 'ArrowLeft':
            window.handleGesture('left');
            break;
        case 'ArrowRight':
            window.handleGesture('right');
            break;
        case 'Enter':
        case ' ':
            window.handleGesture('select');
            break;
    }
});

// ----------------------------------------------------
// WebSocket Connection to Python Backend
// ----------------------------------------------------
function connectWebSocket() {
    const ws = new WebSocket('ws://localhost:8765');

    ws.onopen = function() {
        console.log('Connected to Python Gesture Server');
        const display = document.getElementById('gesture-display');
        if(display) display.textContent = "Connected to Python Server";
    };

    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.gesture) {
                window.handleGesture(data.gesture);
            }
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };

    ws.onclose = function() {
        console.log('Disconnected from Python Server, retrying in 2s...');
        setTimeout(connectWebSocket, 2000); // Auto-reconnect
    };

    ws.onerror = function(error) {
        console.error('WebSocket Error:', error);
    };
}

// Start connection
connectWebSocket();
