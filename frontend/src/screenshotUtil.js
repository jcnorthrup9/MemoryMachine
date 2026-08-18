// Header.jsx's screencap button -- captures whatever the active tab's main
// visual is and downloads it as a PNG. Two capture strategies, chosen by
// tab rather than sniffed generically, since the two visual tabs use
// fundamentally different rendering:
//   - RECONSTRUCT: a Three.js WebGL <canvas> (Viewport.jsx's <Canvas
//     gl={{ preserveDrawingBuffer: true, ... }}>, already configured for
//     this -- without preserveDrawingBuffer, canvas.toDataURL() would
//     return a blank frame since WebGL clears its backbuffer after
//     compositing).
//   - Every other tab that has visual content (SPATIALIZE) draws into an
//     <svg> (spatializerEngine.js's render()), which toDataURL() can't
//     touch directly -- serialize it and rasterize through an offscreen
//     canvas instead.
// DRAWINGS/ARCHIVE/DIAGNOSTICS have no single dominant canvas/svg to
// capture; the button is a no-op there rather than grabbing an arbitrary
// DOM screenshot of unrelated UI chrome.
export async function captureAppScreenshot(activeTab) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const filename = `memory-machine-${activeTab.toLowerCase()}-${timestamp}.png`;

  let dataUrl = null;
  if (activeTab === 'RECONSTRUCT') {
    const canvas = document.querySelector('main canvas');
    if (canvas) dataUrl = canvas.toDataURL('image/png');
  } else {
    const svg = document.querySelector('main svg');
    if (svg) dataUrl = await svgToPngDataUrl(svg);
  }

  if (!dataUrl) return false;

  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
  return true;
}

function svgToPngDataUrl(svg, scale = 2) {
  return new Promise((resolve, reject) => {
    const rect = svg.getBoundingClientRect();
    const width = Math.max(1, Math.round(rect.width * scale));
    const height = Math.max(1, Math.round(rect.height * scale));

    // Clone rather than serialize the live node directly -- explicit
    // pixel width/height (the live SVG only has a CSS width:100%/height:
    // 100%) so the rasterized image isn't 0x0 or viewport-dependent.
    const clone = svg.cloneNode(true);
    clone.setAttribute('width', rect.width);
    clone.setAttribute('height', rect.height);
    const svgString = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      // The live SVG's own background is set via the viewer's page
      // background, not the SVG itself -- white matches the app's
      // current light background so the export doesn't come out
      // transparent/black.
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = (e) => { URL.revokeObjectURL(url); reject(e); };
    img.src = url;
  });
}
