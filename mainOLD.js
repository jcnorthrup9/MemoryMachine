import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// --- DOM Elements ---
const canvasContainer = document.getElementById('canvas-container');
const promptInput = document.getElementById('prompt-input');
const narrativeOutput = document.getElementById('narrative-output');
const diagramContainer = document.getElementById('diagram-container');

// --- Three.js Scene Setup ---
let scene, camera, renderer, controls;
const memoryObjects = new THREE.Group(); // Group to hold generated objects

function initThree() {
    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x000000);
    scene.fog = new THREE.Fog(0x000000, 20, 100);

    // Camera
    camera = new THREE.PerspectiveCamera(75, canvasContainer.clientWidth / canvasContainer.clientHeight, 0.1, 1000);
    camera.position.set(10, 10, 10);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(canvasContainer.clientWidth, canvasContainer.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    canvasContainer.appendChild(renderer.domElement);

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 5;
    controls.maxDistance = 50;
    controls.maxPolarAngle = Math.PI / 2;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x404040, 2);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.5);
    directionalLight.position.set(5, 10, 7.5);
    scene.add(directionalLight);

    // Ground Plane
    const groundGeo = new THREE.PlaneGeometry(100, 100);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8, metalness: 0.2 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);

    // Add object group to scene
    scene.add(memoryObjects);

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }
    animate();

    // Handle Resize
    window.addEventListener('resize', onWindowResize, false);
}

function onWindowResize() {
    camera.aspect = canvasContainer.clientWidth / canvasContainer.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(canvasContainer.clientWidth, canvasContainer.clientHeight);
}

// --- API & Rendering Logic ---

function addNarrativeLine(text, className = '') {
    const pre = document.createElement('pre');
    pre.textContent = text;
    if (className) {
        pre.classList.add(className);
    }
    narrativeOutput.appendChild(pre);
    narrativeOutput.scrollTop = narrativeOutput.scrollHeight;
}

async function handlePromptSubmit() {
    const prompt = promptInput.value.trim();
    if (!prompt) return;

    addNarrativeLine(`> ${prompt}`);
    promptInput.value = '';
    addNarrativeLine('...[PROCESSING MEMORY FRAGMENT]...');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        // Clear previous objects
        while (memoryObjects.children.length > 0) {
            memoryObjects.remove(memoryObjects.children[0]);
        }

        // Add new objects
        data.geometries.forEach(geom => {
            let mesh;
            const material = new THREE.MeshStandardMaterial({ color: geom.color || 0xffffff, roughness: 0.5 });
            
            if (geom.type === 'box') {
                const geometry = new THREE.BoxGeometry(...geom.args);
                mesh = new THREE.Mesh(geometry, material);
            } else if (geom.type === 'cylinder') {
                const geometry = new THREE.CylinderGeometry(...geom.args);
                mesh = new THREE.Mesh(geometry, material);
            } else if (geom.type === 'sphere') {
                const geometry = new THREE.SphereGeometry(...geom.args);
                mesh = new THREE.Mesh(geometry, material);
            }

            if (mesh) {
                mesh.position.set(...geom.position);
                memoryObjects.add(mesh);
            }
        });

        // Update narrative and diagram
        addNarrativeLine(data.narrative, 'success');
        renderMermaid(data.diagram);

    } catch (error) {
        addNarrativeLine(`[ERROR]: ${error.message}`, 'error');
        console.error('Error fetching from API:', error);
    }
}

async function renderMermaid(graphDefinition) {
    mermaid.initialize({ startOnLoad: false, theme: 'dark' });
    const { svg } = await mermaid.render('mermaid-graph', graphDefinition);
    diagramContainer.querySelector('.mermaid').innerHTML = svg;
}

// --- Event Listeners ---
promptInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
        handlePromptSubmit();
    }
});

// --- Initialization ---
initThree();
renderMermaid(`graph TD
    A["Start"] --> B["Waiting for User Input"];`);