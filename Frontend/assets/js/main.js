// assets/js/main.js

// Step Navigation
function nextStep(current, next) {
    document.getElementById(`step-${current}`).classList.remove('active');
    document.getElementById(`step-${next}`).classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Camera Engine
let stream = null;
const videoElement = document.getElementById('camera-preview');
const cameraSection = document.getElementById('camera-section');
let currentCaptureTarget = '';

async function openCamera(target) {
    currentCaptureTarget = target;
    cameraSection.style.display = 'block';
    videoElement.style.display = 'block';
    
    try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        videoElement.srcObject = stream;
    } catch (err) {
        console.error("Error accessing camera: ", err);
        alert("Unable to access camera. Please check permissions or use the file upload option.");
        closeCamera();
    }
}

function closeCamera() {
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
    cameraSection.style.display = 'none';
    videoElement.style.display = 'none';
}

document.getElementById('capture-btn')?.addEventListener('click', () => {
    alert(`Photo captured for ${currentCaptureTarget}!`);
    closeCamera();
});

// Loading Overlay & Extraction Simulation
const overlay = document.getElementById('loading-overlay');
const progressFill = document.getElementById('loading-progress');
const loadingText = document.getElementById('loading-text');

const stages = [
    { text: "Scanning raw image bytes...", progress: 25, delay: 1000 },
    { text: "Computing SHA-256 digital fingerprint hash...", progress: 50, delay: 1500 },
    { text: "Running Tesseract OCR text extraction...", progress: 75, delay: 1500 },
    { text: "Verifying invoice date and serial number match...", progress: 100, delay: 1500 }
];

function processExtraction() {
    // Hide Step 2, show overlay
    document.getElementById('step-2').classList.remove('active');
    overlay.style.display = 'flex';
    
    let currentStage = 0;
    
    function runStage() {
        if (currentStage < stages.length) {
            loadingText.innerText = stages[currentStage].text;
            progressFill.style.width = stages[currentStage].progress + '%';
            
            setTimeout(() => {
                currentStage++;
                runStage();
            }, stages[currentStage-1]?.delay || 1000);
        } else {
            // Done loading
            setTimeout(() => {
                overlay.style.display = 'none';
                progressFill.style.width = '0%';
                // Show step 4
                document.getElementById('step-4').classList.add('active');
            }, 500);
        }
    }
    
    runStage();
}

// Final Outcome Simulator
function showOutcome(type) {
    const container = document.getElementById('outcome-container');
    
    if (type === 'valid') {
        container.innerHTML = `
            <i class="fa-solid fa-circle-check text-olive mb-3" style="font-size: 4rem;"></i>
            <h3 class="text-dark mb-2">Claim Auto-Approved</h3>
            <div class="badge-valid mb-4">98.5% Confidence Score</div>
            <p class="text-muted px-lg-5 mb-5">Your warranty claim has passed multi-modal AI verification. All document hashes match the manufacturer database, and date validity is confirmed.</p>
            <button class="btn btn-olive"><i class="fa-solid fa-file-pdf me-2"></i>Download PDF Audit Certificate</button>
            <button class="btn btn-outline-olive ms-2" onclick="location.reload()">File Another Claim</button>
        `;
    } else if (type === 'invalid') {
        container.innerHTML = `
            <i class="fa-solid fa-circle-xmark text-danger mb-3" style="font-size: 4rem;"></i>
            <h3 class="text-dark mb-2">Claim Rejected</h3>
            <div class="badge-invalid mb-4">Duplicate Receipt Hash</div>
            <p class="text-muted px-lg-5 mb-5">AI analysis detected that this receipt fingerprint has already been used in a previous claim (Claim ID: #C-9021). The claim cannot be processed.</p>
            <button class="btn btn-outline-olive ms-2" onclick="location.reload()">Return to Dashboard</button>
        `;
    } else if (type === 'review') {
        container.innerHTML = `
            <i class="fa-solid fa-triangle-exclamation text-gold mb-3" style="font-size: 4rem;"></i>
            <h3 class="text-dark mb-2">Manual Review Required</h3>
            <div class="badge-review mb-4">Flagged for Human Escalation</div>
            <p class="text-muted px-lg-5 mb-5">The AI model detected discrepancies between the extracted purchase date and the warranty window. This claim has been queued for our support team to review manually.</p>
            <button class="btn btn-olive">Contact Support Team</button>
            <button class="btn btn-outline-olive ms-2" onclick="location.reload()">Return Home</button>
        `;
    }
}
