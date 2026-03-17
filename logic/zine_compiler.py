import os
import re
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Machine // Palimpsest Zine</title>
    <style>
        :root {
            --bg-color: #050505;
            --text-color: #e0e0e0;
            --accent-glow: #fff4ca;
            --border-dim: #222;
            --trans-speed: 0.4s;
        }
        * { box-sizing: border-box; }
        body { background-color: var(--bg-color); color: var(--text-color); font-family: 'Courier New', Courier, monospace; margin: 0; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        .zine-viewer { width: 96vw; max-width: 1800px; height: 92vh; background-color: #000; border: 1px solid var(--border-dim); display: flex; flex-direction: column; position: relative; }
        .spread-container { flex-grow: 1; display: flex; position: relative; overflow: hidden; z-index: 2; }
        .spine { position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: var(--border-dim); z-index: 10; }
        
        .binary-texture { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0.05; font-size: 0.6rem; line-height: 1.1; color: #fff; overflow: hidden; z-index: 1; user-select: none; word-wrap: break-word; pointer-events: none; }
        
        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; transition: all var(--trans-speed) cubic-bezier(0.2, 0.8, 0.2, 1); }
        .left-page { padding: 60px 100px 60px 60px; } 
        .right-page { padding: 60px 60px 60px 100px; } 

        .grid-layout { display: grid; grid-template-columns: repeat(12, 1fr); grid-template-rows: auto 1fr; gap: 20px; height: 100%; }
        
        .abstract-flow { column-count: 2; column-gap: 40px; column-rule: 1px solid #1a1a1a; text-align: justify; text-align-last: left; font-size: 0.85rem; line-height: 1.6; color: #bbb; height: 100%; column-fill: balance; overflow: hidden; grid-column: 1 / -1; transition: all var(--trans-speed) ease-out; }
        
        .vessel { display: flex; flex-direction: column; height: 100%; overflow: hidden; transition: all var(--trans-speed) ease-out; }
        .vessel-span-8 { grid-column: span 8; }
        .vessel-span-4 { grid-column: span 4; border-left: 1px solid var(--border-dim); padding-left: 20px; }
        
        .vignette { border-left: 1px solid var(--accent-glow); padding-left: 20px; margin-bottom: 30px; font-size: 0.85em; color: #aaa; text-align: left; }
        h1.zine-title { font-size: 3rem; color: var(--accent-glow); margin-bottom: 5px; transition: all var(--trans-speed) ease-out; }
        h2.page-header { color: #444; font-size: 0.8rem; text-transform: uppercase; border-bottom: 1px solid #111; padding-bottom: 10px; margin-bottom: 30px; flex-shrink: 0; grid-column: 1 / -1; transition: all var(--trans-speed) ease-out; }
        
        pre { margin: 0; font-size: 0.7rem; line-height: 1.4; color: #555; white-space: pre-wrap; transition: all var(--trans-speed) ease-out; }
        .json-block { color: #88ff88; text-align: left; width: 100%; }
        .binary-block { color: #444; letter-spacing: 3px; text-align: center; font-size: 0.65rem; }
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; }
        .nav-controls button:hover { background: #111; border-color: #444; }

        .matrix-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; width: 100%; align-content: start; }
        .matrix-item { background: #080808; border: 1px solid #111; position: relative; display: flex; flex-direction: column; }
        .matrix-item img { width: 100%; aspect-ratio: 4/3; object-fit: cover; object-position: center; display: block; }
        .matrix-label { padding: 8px; font-size: 0.6rem; color: #888; text-transform: uppercase; text-align: center; border-top: 1px solid #111; letter-spacing: 1px; }

        .single-image-view { width: 100%; height: 100%; display: flex; flex-direction: column; border: 1px solid #111; background: #080808; }
        .single-image-view img { flex-grow: 1; width: 100%; height: 100%; object-fit: contain; object-position: center; display: block; }
        .single-image-view .matrix-label { border-top: 1px solid #111; padding: 10px; font-size: 0.7rem; color: #aaa; text-transform: uppercase; letter-spacing: 2px; text-align: center; }

        .yearbook-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; }
        .yearbook-entry { display: flex; flex-direction: column; align-items: center; }
        .yearbook-placeholder { width: 100%; aspect-ratio: 1; background: #0a0a0a; border: 1px dashed #333; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.6rem; overflow: hidden; }
        .yearbook-placeholder img { width: 100%; height: 100%; object-fit: cover; }
        .yearbook-label { margin-top: 5px; font-size: 0.55rem; color: #666; text-transform: uppercase; text-align: center; letter-spacing: 1px; }

        @keyframes fade-in-image {
            from { opacity: 0; transform: scale(0.98); }
            to { opacity: 1; transform: scale(1); }
        }
        .watercolor-image {
            opacity: 0;
        }
        .spread.active .watercolor-image {
            animation: fade-in-image 1.5s ease-out 0.4s forwards;
        }

        /* GHOST FRAGMENTS (Memory Leakage) */
        .ghost-fragment {
            position: absolute;
            pointer-events: none;
            opacity: 0.6;
            z-index: 50;
            filter: grayscale(1) contrast(2) pixelate(4px);
            mix-blend-mode: hard-light;
            transform: rotate(var(--r, 0deg)) scale(var(--s, 1));
            animation: ghost-flicker 4s infinite ease-in-out, ghost-shift 8s infinite ease-in-out;
            max-width: 300px;
            /* Pixel Trace Simulation */
            box-shadow: 2px 0 0 rgba(255,0,0,0.5), -2px 0 0 rgba(0,0,255,0.5);
            overflow: hidden;
            border: 1px solid red;
            background: #000;
        }
        @keyframes ghost-flicker {
            0% { opacity: 0; clip-path: inset(0 0 0 0); filter: blur(0px); }
            20% { opacity: 0.4; clip-path: polygon(10% 0, 90% 0, 100% 100%, 0 90%); filter: blur(2px) hue-rotate(45deg); }
            50% { opacity: 0.7; clip-path: polygon(0 0, 100% 10%, 100% 90%, 0 100%); filter: blur(1px) hue-rotate(90deg); }
            80% { opacity: 0.3; clip-path: polygon(20% 0, 80% 0, 100% 100%, 0 100%); filter: blur(4px) hue-rotate(135deg); }
            100% { opacity: 0; clip-path: inset(0 0 0 0); filter: blur(10px); }
        }
        @keyframes ghost-shift {
            0% { translate: 0 0; }
            20% { translate: 10px -10px; }
            40% { translate: -15px 15px; }
            60% { translate: 20px 5px; }
            80% { translate: -10px -20px; }
            100% { translate: 0 0; }
        }

        /* INVISIBLE STABILIZER BUTTON */
        .stability-btn {
            position: absolute;
            top: 0;
            right: 0;
            width: 150px;
            height: 150px;
            z-index: 10000;
            cursor: crosshair;
        }
        .stability-btn:active { background-color: rgba(255, 255, 255, 0.05); }

        /* STAGE 1: SUBTLE DECAY (30s mark) */
        @keyframes subtle-rot {
            0% { filter: hue-rotate(0deg) blur(0px); opacity: 1; }
            50% { filter: hue-rotate(5deg) blur(0.5px) sepia(0.2); opacity: 0.95; }
            100% { filter: hue-rotate(0deg) blur(0px); opacity: 1; }
        }
        body.degrading-mild .spread-container { animation: subtle-rot 6s infinite ease-in-out; }

        /* STAGE 2: SYSTEM FAILURE (60s mark) */
        @keyframes datamosh-freeze {
            0% { filter: none; transform: none; clip-path: inset(0 0 0 0); }
            20% { filter: contrast(1.2) hue-rotate(20deg) blur(2px); transform: scale(1.02) skewX(2deg); }
            40% { filter: contrast(1.5) hue-rotate(40deg) blur(4px); transform: translate(-5px, 5px) skewY(2deg); clip-path: polygon(0 0, 100% 10%, 100% 100%, 0 90%); }
            60% { filter: contrast(2) hue-rotate(90deg) blur(8px); transform: scale(1.1) rotate(1deg); clip-path: inset(5% 10% 5% 5%); }
            80% { filter: contrast(3) hue-rotate(180deg) blur(12px) opacity(0.8); transform: scale(1.2) translate(10px, -10px); }
            100% { filter: contrast(4) grayscale(1) blur(20px) opacity(0); transform: scale(1.3) rotate(5deg); pointer-events: none; }
        }
        @keyframes gpu-tear {
            0% { transform: translate(0,0) skew(0deg); clip-path: inset(0 0 0 0); filter: none; }
            20% { transform: translate(-2px, 1px) skew(5deg); clip-path: polygon(0 0, 100% 2%, 100% 98%, 0 100%); filter: blur(1px); }
            40% { transform: translate(4px, -4px) skew(-10deg); clip-path: polygon(5% 0, 95% 0, 100% 100%, 0 100%); filter: contrast(1.5) blur(2px); }
            60% { transform: translate(-5px, 5px) skew(20deg); clip-path: polygon(0 10%, 100% 0, 90% 100%, 10% 100%); filter: hue-rotate(90deg) blur(4px); }
            80% { transform: translate(10px, -10px) skew(-30deg) scale(1.1); clip-path: polygon(0 0, 50% 10%, 100% 0, 100% 100%, 50% 90%, 0 100%); filter: hue-rotate(180deg) blur(8px); }
            100% { transform: translate(50px, 50px) scale(1.2); opacity: 0; filter: blur(15px); }
        }

        /* Apply severe damage to content, but keep container cleaner for longer */
        body.degrading-severe .spread-container { animation: datamosh-freeze 45s cubic-bezier(0.7, 0, 0.84, 0) forwards; }
        body.degrading-severe .page-side h1, 
        body.degrading-severe .page-side h2, 
        body.degrading-severe .page-side p, 
        body.degrading-severe .page-side img { animation: gpu-tear 40s steps(60) forwards; }
        
        /* Button Reboot State */
        .nav-controls button.reboot-mode {
            background-color: #f00;
            color: #000;
            border: 1px solid #f00;
            animation: glitch-anim 0.2s infinite;
            font-weight: bold;
        }

        @keyframes glitch-anim {
            0% { clip-path: polygon(0 2%, 100% 2%, 100% 5%, 0 5%); transform: translate(0, 0) skew(0); }
            20% { clip-path: polygon(0 15%, 100% 15%, 100% 15%, 0 15%); transform: translate(-25px, 2px) skew(40deg); }
            40% { clip-path: polygon(0 10%, 100% 10%, 100% 20%, 0 20%); transform: translate(25px, -2px) skew(-40deg); }
            60% { clip-path: polygon(0 1%, 100% 1%, 100% 2%, 0 2%); transform: translate(15px, 0) skew(15deg); }
            80% { clip-path: polygon(0 33%, 100% 33%, 100% 33%, 0 33%); transform: translate(-15px, 2px) skew(-10deg); }
            100% { clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%); transform: translate(0, 0) skew(0); }
        }

        body.glitch-mode .page-side { animation: glitch-anim 0.6s infinite steps(2); filter: invert(1); }
        body.glitch-mode .left-page { transform: translateX(20px) rotate(-1deg); }
        body.glitch-mode .right-page { transform: translateX(-20px) rotate(1deg); margin-left: -50px; }
        body.glitch-mode h1, body.glitch-mode h2 { animation: glitch-anim 4s infinite linear alternate-reverse; color: #ff0000; text-shadow: 2px 0 #00ff00; }
        body.glitch-mode pre { animation: glitch-anim 1s infinite; opacity: 0.5; }
        body.glitch-mode .binary-texture { animation: glitch-anim 0.2s infinite reverse; color: #00ff00; opacity: 0.2; }

        /* PRINT CONFIGURATION */
        @media print {
            @page { size: letter landscape; margin: 0; }
            html, body { display: block !important; width: 100%; height: auto !important; overflow: visible !important; background-color: #050505 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
            .zine-viewer { display: block !important; width: 100%; height: auto !important; max-width: none; border: none; position: static; overflow: visible; margin: 0 !important; }
            .spread-container { display: block !important; position: static; overflow: visible; height: auto !important; }
            .spine, .nav-controls, .stability-btn, .binary-texture, #page-indicator { display: none !important; }
            
            .spread { display: flex !important; position: relative !important; width: 100%; height: 100vh !important; page-break-after: always; break-after: page; top: auto; left: auto; opacity: 1 !important; visibility: visible !important; }
            
            /* Print-Specific Glitch Adjustments: Remove blend modes for safer CMYK conversion */
            .ghost-fragment { mix-blend-mode: normal !important; opacity: 0.7 !important; filter: contrast(1.5) grayscale(1); border-color: #ff0000 !important; }
            .watercolor-image { opacity: 1 !important; animation: none !important; }
            
            .page-break { break-after: page; page-break-after: always; }
        }
    </style>
</head>
<body>
    <div class="zine-viewer">
        <div class="stability-btn" onclick="resetDegradation()" title="[ MANUAL OVERRIDE ]"></div>
        <div class="binary-texture">{{BINARY_DATA_1988}}</div>
        
        <div class="spread-container">
            <div class="spine"></div>

            <div class="spread active" id="spread-1" style="justify-content: center; align-items: center; flex-direction: column; background-color: #030303; z-index: 10;">
                <div style="text-align: center; width: 80%; max-width: 1400px; padding: 40px; position: relative; z-index: 10;">
                    <h1 class="zine-title" style="font-size: 5rem; margin-bottom: 10px;">Forensic_Palimpsest</h1>
                    <div style="letter-spacing: 8px; color: #666; margin-bottom: 60px; font-size: 1.2rem;">THE MEMORY MACHINE // JOHN C. NORTHRUP II</div>
                    <img src="../archive/render_output/front_cover.jpg" style="width: 100%; max-height: 65vh; object-fit: contain; border: 1px solid var(--border-dim); filter: grayscale(100%); box-shadow: 0 0 40px rgba(0,0,0,0.8);">
                </div>
            </div>

            <div class="spread" id="spread-2">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">01 // Table of Contents</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre style="color: #666; font-size: 1rem;">{{TOC_DATA}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">02 // System Pipeline Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre style="color: #666; font-size: 1rem;">{{PIPELINE_DATA}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-3">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">03 // The Machine That Forgets // I</h2>
                        <div class="abstract-flow">{{ABSTRACT_1}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">04 // The Machine That Forgets // II</h2>
                        <div class="abstract-flow">{{ABSTRACT_2}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-4">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">05 // The Machine That Forgets // III</h2>
                        <div class="abstract-flow">{{ABSTRACT_3}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">06 // The Machine That Forgets // IV</h2>
                        <div class="abstract-flow">{{ABSTRACT_4}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-5">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">07 // The Machine That Forgets // V</h2>
                        <div class="abstract-flow">{{ABSTRACT_5}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">08 // The Machine That Forgets // VI</h2>
                        <div class="abstract-flow">{{ABSTRACT_6}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-6">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">09 // Forensic Asset Catalog // A</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{YEARBOOK_1}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">10 // Forensic Asset Catalog // B</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{YEARBOOK_2}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-7">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">11 // Node: 1988_Trailer // Narrative</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{NARRATIVE_DATA_1988}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">12 // Memory Construct // Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre class="json-block" style="font-size: 1.1rem;">{{JSON_DATA_1988}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-8">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">13 // Binary Strata</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; justify-content: center; overflow-y: auto;">
                            <pre style="color: #666; font-size: 1.1rem; white-space: pre-wrap;">{{BINARY_DATA_1988}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">14 // Rendering Layer</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                            <img src="../archive/render_output/1988_trailer.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222;">
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-9">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">15 // 1988 Watercolor Study // A</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                             <img class="watercolor-image" src="../archive/render_output/1988_trailerWatercolor.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222;">
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">16 // 1988 Watercolor Study // B</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                             <img class="watercolor-image" src="../archive/render_output/1988_trailerwatercolorInterior2.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222;">
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-10">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">17 // Node: 1992_Birthday // Narrative</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{NARRATIVE_DATA_1992}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">18 // Memory Construct // Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre class="json-block" style="font-size: 1.1rem;">{{JSON_DATA_1992}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-11">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">19 // Binary Strata</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; justify-content: center; overflow-y: auto;">
                            <pre style="color: #666; font-size: 1.1rem; white-space: pre-wrap;">{{BINARY_DATA_1992}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">20 // Rendering Layer</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                            <img src="../archive/render_output/1992_birthday.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222;">
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-12">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">21 // Node: 1994_Basin // Narrative</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{NARRATIVE_DATA_1994}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">22 // Memory Construct // Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre class="json-block" style="font-size: 1.1rem;">{{JSON_DATA_1994}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-13">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">23 // Binary Strata</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; justify-content: center; overflow-y: auto;">
                            <pre style="color: #666; font-size: 1.1rem; white-space: pre-wrap;">{{BINARY_DATA_1994}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">24 // Rendering Layer</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                            <img src="../archive/render_output/1994_basin.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222;">
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-14">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">25 // Precedent: Aldo Rossi</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_ROSSI}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">26 // Theory: Architectural Memory</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <div class="abstract-flow" style="column-count: 1;">{{ARCH_MEMORY_TEXT}}</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-15">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">27 // Precedent: Neu Museum // I</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_NEU_L}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">28 // Precedent: Neu Museum // II</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_NEU_R}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-16">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">29 // Precedent: Zeitz MOCAA // I</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_ZEITZ_L}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">30 // Precedent: Zeitz MOCAA // II</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_ZEITZ_R}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-17">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">31 // Precedent: Genbaku Dome // I</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_GENBAKU_L}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">32 // Precedent: Genbaku Dome // II</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_GENBAKU_R}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-18">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">33 // Precedent: Do Ho Suh // I</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_DOSOSUH_L}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">34 // Precedent: Do Ho Suh // II</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{PRECEDENTS_DOSOSUH_R}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-19">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">35 // References</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <div class="abstract-flow">{{REFERENCES_DATA}}</div>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">36 // System Status</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center;">
                            <div style="color: #333; font-size: 0.8rem;">[ PROCESS TERMINATED ]</div>
                        </div>
                    </div>
                </div>
            </div>

        </div>

        <footer class="zine-footer">
            <div id="page-indicator">I</div>
            <div class="nav-controls">
                <button id="btn-prev" onclick="prevSpread()">[ PREV ]</button>
                <button id="btn-next" onclick="nextSpread()">[ NEXT ]</button>
            </div>
        </footer>
    </div>

    <script>
        const totalSpreads = 19;
        let mildTimeout;
        let severeTimeout;
        let artifactInterval;
        let glitchInterval;

        function resetDegradation() {
            document.body.classList.remove('degrading-mild');
            document.body.classList.remove('degrading-severe');
            
            // Clear ghost artifacts
            document.querySelectorAll('.ghost-fragment').forEach(el => el.remove());
            
            // Reset Button
            const nextBtn = document.getElementById('btn-next');
            nextBtn.innerText = "[ NEXT ]";
            nextBtn.classList.remove('reboot-mode');
            nextBtn.onclick = nextSpread;
            
            clearInterval(artifactInterval);
            clearTimeout(mildTimeout);
            clearTimeout(severeTimeout);
            
            // Start Timer: 30s to mild decay
            mildTimeout = setTimeout(() => {
                document.body.classList.add('degrading-mild');
                
                // +30s (total 60s) to severe failure
                severeTimeout = setTimeout(startSystemFailure, 30000);
            }, 30000); 
        }

        function startSystemFailure() {
            document.body.classList.remove('degrading-mild');
            document.body.classList.add('degrading-severe');
            
            // Start leaking memories (stacking fragments)
            artifactInterval = setInterval(injectArtifact, 800);

            // Schedule System Break (Button Change)
            setTimeout(() => {
                const nextBtn = document.getElementById('btn-next');
                nextBtn.innerText = "[ REINITIALIZE ]";
                nextBtn.classList.add('reboot-mode');
                nextBtn.onclick = () => location.reload();
                clearInterval(artifactInterval); // Stop adding new ones, freeze state
            }, 30000);
        }

        function injectArtifact() {
            // Grab content from a random hidden spread
            const hiddenSpreads = document.querySelectorAll('.spread:not(.active)');
            if (hiddenSpreads.length === 0) return;
            
            const randomSpread = hiddenSpreads[Math.floor(Math.random() * hiddenSpreads.length)];
            const targets = randomSpread.querySelectorAll('p, h1, h2, img, pre');
            if (targets.length === 0) return;
            
            const source = targets[Math.floor(Math.random() * targets.length)];
            const clone = source.cloneNode(true);
            
            clone.classList.add('ghost-fragment');
            
            // Random positioning and distortion
            clone.style.top = Math.random() * 80 + '%';
            clone.style.left = Math.random() * 80 + '%';
            
            // Set variables for the CSS transform to use, allowing keyframes to translate independently
            clone.style.setProperty('--r', `${Math.random() * 360}deg`);
            clone.style.setProperty('--s', `${0.5 + Math.random()}`);
            
            // Inner fracture: Apply random polygon clip to the artifact itself
            const p1 = Math.floor(Math.random() * 100);
            const p2 = Math.floor(Math.random() * 100);
            clone.style.clipPath = `polygon(0% 0%, 100% 0%, 100% ${p1}%, ${p2}% 100%, 0% 100%)`;

            document.querySelector('.zine-viewer').appendChild(clone);
            
            // Prevent total DOM crash by limiting artifacts
            const ghosts = document.querySelectorAll('.ghost-fragment');
            if (ghosts.length > 40) ghosts[0].remove();
        }

        // INITIAL LOAD SEQUENCE
        setTimeout(() => {
            document.body.classList.add('glitch-mode');
            glitchInterval = setInterval(() => {
                const randomSpread = Math.floor(Math.random() * totalSpreads) + 1;
                showSpread(randomSpread, true);
            }, 200);
        }, 2000); // Start glitching after 2s

        setTimeout(() => {
            clearInterval(glitchInterval);
            document.body.classList.remove('glitch-mode');
            showSpread(1, true);
            resetDegradation(); // Start the degradation timer once stabilized
        }, 5000); // Stop glitching after 5s

        let currentSpread = 1;
        function showSpread(n, suppressGlitch) {
            resetDegradation();
            
            // Random transition speed variation: 1-5% variance on 0.4s base (very subtle, organic feel)
            const baseSpeed = 0.4;
            const variance = baseSpeed * (Math.random() * 0.04 + 0.01) * (Math.random() < 0.5 ? -1 : 1);
            document.documentElement.style.setProperty('--trans-speed', (baseSpeed + variance) + 's');

            if (!suppressGlitch) {
                document.body.classList.add('glitch-mode');
                setTimeout(() => {
                    document.body.classList.remove('glitch-mode');
                }, 260);
            }
            document.querySelectorAll('.spread').forEach(s => s.classList.remove('active'));
            document.getElementById(`spread-${n}`).classList.add('active');
            const labels = ["I", "II // SYSTEM", "III // THEORY A", "IV // THEORY B", "V // THEORY C", "VI // CATALOG", "VII // 1988 TRAILER", "VIII // 1988 RENDER", "IX // 1988 WATERCOLORS", "X // 1992 BIRTHDAY", "XI // 1992 RENDER", "XII // 1994 BASIN", "XIII // 1994 RENDER", "XIV // ROSSI", "XV // NEU MUSEUM", "XVI // ZEITZ MOCAA", "XVII // GENBAKU", "XVIII // DO HO SUH", "XIX // REFERENCES"];
            document.getElementById('page-indicator').innerText = labels[n-1];
            currentSpread = n;
        }
        function nextSpread() { currentSpread < totalSpreads ? showSpread(currentSpread + 1) : showSpread(1); }
        function prevSpread() { currentSpread > 1 ? showSpread(currentSpread - 1) : showSpread(totalSpreads); }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') nextSpread();
            if (e.key === 'ArrowLeft') prevSpread();
        });
    </script>
</body>
</html>"""

def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return f"[MISSING DATA: {filename}]"

def get_asset_grid_html():
    manifest_path = os.path.join(DATA_DIR, 'asset_manifest.csv')
    grid_html = ""
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert absolute project path to relative HTML path (../archive/...)
                # Assuming CSV path is like "archive/assets/thumbnails/image.jpg"
                rel_path = "../" + row['Thumbnail_Path'].replace("\\", "/")
                grid_html += f'<div class="matrix-item"><img src="{rel_path}"></div>'
    # Pad with empty items if needed to maintain grid structure (optional)
    return grid_html

def get_redacted_reviews(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return f"[MISSING DATA: {filename}]"
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Redact all variations of the business name (case-insensitive)
    redacted = re.sub(r'(?i)bottega louie\'s|bottega louie|bottega louis|botegga louie|bottega', '[BUSINESS NAME]', content)
    
    # Split by double-newlines so each block of the review becomes its own vignette
    paragraphs = [p.strip() for p in redacted.split('\n\n') if p.strip()]
    return "---".join(paragraphs)

def compile_zine():
    print("\n--- Waking up the Memory Machine ---")
    
    # Auto-generate System Pipeline Logic based on project files
    pipeline_lines = ["02 // SYSTEM PIPELINE LOGIC", "", "DETECTED PYTHON MODULES:"]
    skip_dirs = {'.git', '__pycache__', 'venv', 'env', '.pytest_cache', 'node_modules', '.vscode'}
    
    for root, dirs, files in os.walk(BASE_DIR):
        dirs.sort()
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        py_files = [f for f in files if f.endswith('.py')]
        if py_files:
            rel_path = os.path.relpath(root, BASE_DIR)
            folder_label = "ROOT" if rel_path == "." else rel_path.upper().replace(os.sep, " :: ")
            
            pipeline_lines.append(f"\n[ {folder_label} ]")
            for f in sorted(py_files):
                pipeline_lines.append(f"   > {f}")
                
    pipeline_data = "\n".join(pipeline_lines)

    # Automatically generate Table of Contents
    toc_lines = [
        "01 // Table of Contents",
        "02 // System Pipeline Logic",
        "03 // The Machine That Forgets // I",
        "04 // The Machine That Forgets // II",
        "05 // The Machine That Forgets // III",
        "06 // The Machine That Forgets // IV",
        "07 // The Machine That Forgets // V",
        "08 // The Machine That Forgets // VI",
        "09 // Forensic Asset Catalog // A",
        "10 // Forensic Asset Catalog // B",
        "11 // Node: 1988_Trailer // Narrative",
        "12 // Node: 1988_Trailer // Logic",
        "13 // Node: 1988_Trailer // Binary",
        "14 // Node: 1988_Trailer // Render",
        "15 // 1988 Watercolor Study // A",
        "16 // 1988 Watercolor Study // B",
        "17 // Node: 1992_Birthday // Narrative",
        "18 // Node: 1992_Birthday // Logic",
        "19 // Node: 1992_Birthday // Binary",
        "20 // Node: 1992_Birthday // Render",
        "21 // Node: 1994_Basin // Narrative",
        "22 // Node: 1994_Basin // Logic",
        "23 // Node: 1994_Basin // Binary",
        "24 // Node: 1994_Basin // Render",
        "25 // Precedent: Aldo Rossi",
        "26 // Theory: Architectural Memory",
        "27 // Precedent: Neu Museum // I",
        "28 // Precedent: Neu Museum // II",
        "29 // Precedent: Zeitz MOCAA // I",
        "30 // Precedent: Zeitz MOCAA // II",
        "31 // Precedent: Genbaku Dome // I",
        "32 // Precedent: Genbaku Dome // II",
        "33 // Precedent: Do Ho Suh // I",
        "34 // Precedent: Do Ho Suh // II",
        "35 // References",
        "36 // System Status"
    ]
    toc_data = "\n".join(toc_lines)

    abstract = get_data('thesis_abstract.txt')
    
    narrative_1988 = get_data('1988_trailer_parsed.txt')
    json_1988 = get_data('1988_trailer_logic.json')
    binary_1988 = get_data('1988_trailer_binary_strata.txt')

    narrative_1992 = get_data('1992_birthday_parsed.txt')
    json_1992 = get_data('1992_birthday_logic.json')
    binary_1992 = get_data('1992_birthday_binary_strata.txt')

    narrative_1994 = get_data('1994_basin_parsed.txt')
    json_1994 = get_data('1994_basin_logic.json')
    binary_1994 = get_data('1994_basin_binary_strata.txt')

    references = get_data('references.txt')

    words = abstract.split()
    if len(words) > 0:
        chunk = len(words) // 6 + 1
        abs_1 = " ".join(words[:chunk])
        abs_2 = " ".join(words[chunk:chunk*2])
        abs_3 = " ".join(words[chunk*2:chunk*3])
        abs_4 = " ".join(words[chunk*3:chunk*4])
        abs_5 = " ".join(words[chunk*4:chunk*5])
        abs_6 = " ".join(words[chunk*5:])
    else:
        abs_1 = abs_2 = abs_3 = abs_4 = abs_5 = abs_6 = ""

    def process_vignettes(text):
        if "MISSING DATA" in text:
            return f'<div class="vignette" style="color:#666;">{text}</div>'
        snippets = text.split('---')
        return "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    vignette_1988 = process_vignettes(narrative_1988)
    vignette_1992 = process_vignettes(narrative_1992)
    vignette_1994 = process_vignettes(narrative_1994)

    thumb_dir = os.path.join(BASE_DIR, 'archive', 'assets', 'thumbnails')
    yearbook_data = []
    if os.path.exists(thumb_dir):
        for f in sorted(os.listdir(thumb_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                name = os.path.splitext(f)[0].replace('_', ' ').upper()
                img_tag = f'<img src="../archive/assets/thumbnails/{f}">'
                yearbook_data.append((name, img_tag))

    while len(yearbook_data) < 32:
        yearbook_data.append(("{PLACEHOLDER TEXT}", "PENDING"))

    def make_yearbook_grid(items):
        return '<div class="yearbook-grid">' + "".join([f'<div class="yearbook-entry"><div class="yearbook-placeholder">{content}</div><div class="yearbook-label">{name}</div></div>' for name, content in items]) + '</div>'

    yb_1 = make_yearbook_grid(yearbook_data[:16])
    yb_2 = make_yearbook_grid(yearbook_data[16:32])

    precedents_dir = os.path.join(BASE_DIR, 'archive', 'precedents')
    
    # Categorize images by keywords
    groups = {
        "rossi": [],
        "neu": [],
        "zeitz": [],
        "genbaku": [],
        "dohosuh": []
    }
    
    if os.path.exists(precedents_dir):
        print(f"   > Scanning directory: {precedents_dir}")
        all_files = sorted(os.listdir(precedents_dir))
        for f in all_files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                name = f.lower()
                print(f"   > Processing precedent: {f}")
                if "rossi" in name: groups["rossi"].append(f)
                elif "neu" in name: groups["neu"].append(f)
                elif "zeitz" in name: groups["zeitz"].append(f)
                elif "genbaku" in name: groups["genbaku"].append(f)
                elif "suh" in name or "doho" in name: groups["dohosuh"].append(f)

        print("\n   [ PRECEDENT GROUPS SUMMARY ]")
        for k, v in groups.items():
            print(f"   > {k.upper()}: {len(v)} files found")

    def generate_html_for_group(file_list):
        if not file_list:
            return '<div class="vignette" style="color:#666;">[NO DATA]</div>'
        
        items_html = []
        for f in file_list:
            name = os.path.splitext(f)[0]
            items_html.append(f'<img src="../archive/precedents/{f}"><div class="matrix-label">{name}</div>')
            
        if len(file_list) == 1:
            return f'<div class="single-image-view">{items_html[0]}</div>'
        else:
            grid_content = "".join([f'<div class="matrix-item">{item}</div>' for item in items_html])
            return f'<div class="matrix-grid">{grid_content}</div>'

    def split_group(file_list):
        mid = (len(file_list) + 1) // 2
        return file_list[:mid], file_list[mid:]

    # Rossi (Single Page Left)
    precedents_rossi = generate_html_for_group(groups["rossi"])

    # Neu (Full Spread)
    neu_l, neu_r = split_group(groups["neu"])
    precedents_neu_l = generate_html_for_group(neu_l)
    precedents_neu_r = generate_html_for_group(neu_r)

    # Zeitz (Full Spread)
    zeitz_l, zeitz_r = split_group(groups["zeitz"])
    precedents_zeitz_l = generate_html_for_group(zeitz_l)
    precedents_zeitz_r = generate_html_for_group(zeitz_r)

    # Genbaku (Full Spread)
    genbaku_l, genbaku_r = split_group(groups["genbaku"])
    precedents_genbaku_l = generate_html_for_group(genbaku_l)
    precedents_genbaku_r = generate_html_for_group(genbaku_r)

    # Dososuh (Full Spread)
    dososuh_l, dososuh_r = split_group(groups["dohosuh"])
    precedents_dososuh_l = generate_html_for_group(dososuh_l)
    precedents_dososuh_r = generate_html_for_group(dososuh_r)

    # Extract Architectural Memory Text
    arch_memory_raw = get_data('ThePersistentArtifact.txt')
    arch_memory_text = f"<div class='vignette'>{arch_memory_raw}</div>"

    print("Injecting data into HTML matrix...")
    html = HTML_TEMPLATE.replace('{{ABSTRACT_1}}', abs_1)
    html = html.replace('{{ABSTRACT_2}}', abs_2)
    html = html.replace('{{ABSTRACT_3}}', abs_3)
    html = html.replace('{{ABSTRACT_4}}', abs_4)
    html = html.replace('{{ABSTRACT_5}}', abs_5)
    html = html.replace('{{ABSTRACT_6}}', abs_6)
    html = html.replace('{{TOC_DATA}}', toc_data)
    html = html.replace('{{PIPELINE_DATA}}', pipeline_data)
    
    html = html.replace('{{PRECEDENTS_ROSSI}}', precedents_rossi)
    html = html.replace('{{ARCH_MEMORY_TEXT}}', arch_memory_text)
    html = html.replace('{{PRECEDENTS_NEU_L}}', precedents_neu_l)
    html = html.replace('{{PRECEDENTS_NEU_R}}', precedents_neu_r)
    html = html.replace('{{PRECEDENTS_ZEITZ_L}}', precedents_zeitz_l)
    html = html.replace('{{PRECEDENTS_ZEITZ_R}}', precedents_zeitz_r)
    html = html.replace('{{PRECEDENTS_GENBAKU_L}}', precedents_genbaku_l)
    html = html.replace('{{PRECEDENTS_GENBAKU_R}}', precedents_genbaku_r)
    html = html.replace('{{PRECEDENTS_DOSOSUH_L}}', precedents_dososuh_l)
    html = html.replace('{{PRECEDENTS_DOSOSUH_R}}', precedents_dososuh_r)

    html = html.replace('{{NARRATIVE_DATA_1988}}', vignette_1988)
    html = html.replace('{{JSON_DATA_1988}}', json_1988)
    html = html.replace('{{BINARY_DATA_1988}}', binary_1988)

    html = html.replace('{{NARRATIVE_DATA_1992}}', vignette_1992)
    html = html.replace('{{JSON_DATA_1992}}', json_1992)
    html = html.replace('{{BINARY_DATA_1992}}', binary_1992)

    html = html.replace('{{NARRATIVE_DATA_1994}}', vignette_1994)
    html = html.replace('{{JSON_DATA_1994}}', json_1994)
    html = html.replace('{{BINARY_DATA_1994}}', binary_1994)

    html = html.replace('{{YEARBOOK_1}}', yb_1)
    html = html.replace('{{YEARBOOK_2}}', yb_2)
    html = html.replace('{{REFERENCES_DATA}}', references)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ BUILD SUCCESSFUL: {OUTPUT_FILE} has been updated!\n")

if __name__ == "__main__":
    compile_zine()