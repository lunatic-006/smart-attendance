/**
 * Shared logic for accessing the webcam, capturing frames, and converting to Base64.
 */

let videoElement = null;
let currentStream = null;

async function startCamera(videoElementId) {
    videoElement = document.getElementById(videoElementId);
    if (!videoElement) {
        console.error(`Video element with ID ${videoElementId} not found.`);
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: "user" 
            } 
        });
        currentStream = stream;
        videoElement.srcObject = stream;
        
        // Wait for video to actually start playing
        await new Promise((resolve) => {
            videoElement.onplaying = resolve;
        });
        
        console.log("Camera started successfully.");
    } catch (err) {
        console.error("Error accessing camera:", err);
        alert("Camera access is required for attendance verification. Please allow permissions.");
    }
}

function stopCamera() {
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
    }
}

function captureBase64() {
    if (!videoElement || !currentStream) {
        console.error("Camera is not active.");
        return null;
    }

    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth;
    canvas.height = videoElement.videoHeight;
    
    const ctx = canvas.getContext('2d');
    // Draw the current video frame onto the canvas
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    
    // Get base64 string
    // Uses jpeg for performance, adjust quality [0-1] as needed
    const dataUrl = canvas.toDataURL('image/jpeg', 0.8); 
    
    return dataUrl;
}
