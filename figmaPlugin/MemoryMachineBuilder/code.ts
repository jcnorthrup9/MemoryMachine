figma.showUI(__html__, { width: 320, height: 240 });

figma.ui.onmessage = async (msg) => {
  if (msg.type === 'generate-deck') {
    const payload = msg.payload;
    
    // Load fonts
    await figma.loadFontAsync({ family: "Roboto Mono", style: "Regular" });
    await figma.loadFontAsync({ family: "Roboto Mono", style: "Bold" });

    let xOffset = 0;
    const generatedNodes: SceneNode[] = [];

    // Memory Machine Style Variables matching HTML
    const bgDark = { r: 5/255, g: 5/255, b: 5/255 }; // #050505
    const textLight = { r: 204/255, g: 204/255, b: 204/255 }; // #ccc
    const textDim = { r: 136/255, g: 136/255, b: 136/255 }; // #888
    const accentYellow = { r: 1, g: 244/255, b: 202/255 }; // #fff4ca
    const borderDim = { r: 34/255, g: 34/255, b: 34/255 }; // #222

    // Helper: Force text wrap within boundaries
    function createTextWrap(text: string, size: number, color: RGB, width: number, isBold: boolean = false, noWrap: boolean = false) {
      const node = figma.createText();
      node.fontName = { family: "Roboto Mono", style: isBold ? "Bold" : "Regular" };
      node.fontSize = size;
      node.fills = [{ type: 'SOLID', color }];
      if (noWrap) {
        node.textAutoResize = "WIDTH_AND_HEIGHT";
      } else {
        node.textAutoResize = "HEIGHT";
        node.resize(width, 100); 
      }
      node.characters = text || " ";
      return node;
    }

    for (const slide of payload.slides) {
      const frame = figma.createFrame();
      frame.name = slide.title || "Slide";
      frame.resize(1920, 1080);
      frame.x = xOffset;
      frame.fills = [{ type: 'SOLID', color: bgDark }];
      
      if (slide.type === 'title_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const subNode = createTextWrap(slide.subtitle, 24, textDim, 800);
        frame.appendChild(subNode);
        subNode.x = 80;
        subNode.y = titleNode.y + titleNode.height + 20;

        if (slide.body) {
          const bodyNode = createTextWrap(slide.body, 16, textLight, 800);
          frame.appendChild(bodyNode);
          bodyNode.x = 80;
          bodyNode.y = 250;
        }

        if (slide.hero_image && slide.hero_image.image) {
          const rect = figma.createRectangle();
          frame.appendChild(rect);
          rect.resize(960, 1080);
          rect.x = 960;
          rect.y = 0;
          try {
            const imageBytes = figma.base64Decode(slide.hero_image.image);
            const figmaImage = figma.createImage(imageBytes);
            rect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
          } catch (e) { console.log("Error loading hero image", e); }
        }
      } 
      else if (slide.type === 'text_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body, 16, textLight, 800);
        frame.appendChild(bodyNode);
        bodyNode.x = 80;
        bodyNode.y = 250;
      }
      else if (slide.type === 'text_and_mermaid_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body || " ", 16, textLight, 800);
        frame.appendChild(bodyNode);
        bodyNode.x = 80;
        bodyNode.y = 250;

        const rightTitle = createTextWrap(slide.right_title, 20, textDim, 800, true);
        frame.appendChild(rightTitle);
        rightTitle.x = 1040;
        rightTitle.y = titleNode.y + titleNode.height + 15;

        const rect = figma.createRectangle();
        frame.appendChild(rect);
        rect.resize(800, 800);
        rect.x = 1040;
        rect.y = 250;
        rect.fills = [{ type: 'SOLID', color: {r: 0.03, g: 0.03, b: 0.03} }];
        rect.strokes = [{ type: 'SOLID', color: borderDim }];
        rect.strokeWeight = 1;

        const codeNode = createTextWrap(slide.mermaid_code, 12, {r: 0.5, g: 1.0, b: 0.5}, 760);
        frame.appendChild(codeNode);
        codeNode.x = 1060;
        codeNode.y = rect.y + 20;
      }
      else if (slide.type === 'text_and_image_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body, 16, textLight, 800);
        frame.appendChild(bodyNode);
        bodyNode.x = 80;
        bodyNode.y = 250;

        const rightTitle = createTextWrap(slide.right_title, 20, textDim, 800, true);
        frame.appendChild(rightTitle);
        rightTitle.x = 1040;
        rightTitle.y = titleNode.y + titleNode.height + 15;

        let currentY = 250;
        if (slide.right_grid) {
          for (const item of slide.right_grid) {
            if (!item) continue;
            const rect = figma.createRectangle();
            frame.appendChild(rect);
            rect.resize(800, 400);
            rect.x = 1040;
            rect.y = currentY;
            rect.fills = [{ type: 'SOLID', color: {r: 0.03, g: 0.03, b: 0.03} }];

            if (item.image) {
              try {
                const imageBytes = figma.base64Decode(item.image);
                const figmaImage = figma.createImage(imageBytes);
                rect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
                rect.strokes = [{ type: 'SOLID', color: borderDim }];
                rect.strokeWeight = 1;
              } catch (e) { console.log("Error loading image", e); }
            } else {
              rect.strokes = [{ type: 'SOLID', color: borderDim }];
              rect.strokeWeight = 1;
              rect.dashPattern = [5, 5];
            }

            currentY += 400 + 40;
          }
        }
      }
      else if (slide.type === 'dual_text_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const leftTitle = createTextWrap(slide.left_title, 20, textDim, 800, true);
        frame.appendChild(leftTitle);
        leftTitle.x = 80;
        leftTitle.y = titleNode.y + titleNode.height + 15;

        const leftBody = createTextWrap(slide.left_body, 16, textLight, 800);
        frame.appendChild(leftBody);
        leftBody.x = 80;
        leftBody.y = 250;

        const rightTitle = createTextWrap(slide.right_title, 20, textDim, 800, true);
        frame.appendChild(rightTitle);
        rightTitle.x = 1040;
        rightTitle.y = titleNode.y + titleNode.height + 15;

        const rightBody = createTextWrap(slide.right_body, 16, { r: 0, g: 1, b: 102/255 }, 800);
        frame.appendChild(rightBody);
        rightBody.x = 1040;
        rightBody.y = rightTitle.y + rightTitle.height + 20;

        if (slide.right_image && slide.right_image.image) {
          const rect = figma.createRectangle();
          frame.appendChild(rect);
          rect.resize(800, 600);
          rect.x = 1040;
          rect.y = 250;
          try {
            const imageBytes = figma.base64Decode(slide.right_image.image);
            const figmaImage = figma.createImage(imageBytes);
            rect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
            rect.strokes = [{ type: 'SOLID', color: borderDim }];
            rect.strokeWeight = 1;
          } catch (e) { console.log("Error loading image", e); }
        }
      }
      else if (slide.type === 'grid_slide') {
        // Main Title (Left Page)
        const mainTitleNode = createTextWrap(slide.title, 42, accentYellow, 800, true, true);
        frame.appendChild(mainTitleNode);
        mainTitleNode.x = 80;
        mainTitleNode.y = 40;

        // --- LEFT PAGE GRID ---
        const leftTitle = createTextWrap(slide.left_title, 20, textDim, 800, true);
        frame.appendChild(leftTitle);
        leftTitle.x = 80;
        leftTitle.y = mainTitleNode.y + mainTitleNode.height + 15;

        let gridX = 80;
        let gridY = 250;
        const boxWidth = 800;
        const boxHeight = 400;
        const gap = 40;

        for (let i = 0; i < (slide.left_grid ? slide.left_grid.length : 0); i++) {
          const item = slide.left_grid[i];
          if (!item) continue;
          
          const boxX = gridX; 
          const boxY = gridY + (i * (boxHeight + gap));

          const rect = figma.createRectangle();
          frame.appendChild(rect);
          rect.resize(boxWidth, boxHeight);
          rect.x = boxX;
          rect.y = boxY;
          rect.fills = [{ type: 'SOLID', color: {r: 0.03, g: 0.03, b: 0.03} }];
          
          // Inject base64 image if it exists
          if (item.image) {
            try {
              const imageBytes = figma.base64Decode(item.image);
              const figmaImage = figma.createImage(imageBytes);
              rect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
              rect.strokes = [{ type: 'SOLID', color: borderDim }];
              rect.strokeWeight = 1;
            } catch (e) {
              console.log("Error loading image", e);
            }
          } else {
            // Placeholder Styling
            rect.strokes = [{ type: 'SOLID', color: borderDim }];
            rect.strokeWeight = 1;
            rect.dashPattern = [5, 5];
          }

        }

        // --- RIGHT PAGE GRID ---
        const rightTitle = createTextWrap(slide.right_title, 20, textDim, 800, true);
        frame.appendChild(rightTitle);
        rightTitle.x = 1040;
        rightTitle.y = mainTitleNode.y + mainTitleNode.height + 15;

        gridX = 1040;
        for (let i = 0; i < (slide.right_grid ? slide.right_grid.length : 0); i++) {
          const item = slide.right_grid[i];
          if (!item) continue;
          
          const boxX = gridX;
          const boxY = gridY + (i * (boxHeight + gap));

          const rect = figma.createRectangle();
          frame.appendChild(rect);
          rect.resize(boxWidth, boxHeight);
          rect.x = boxX;
          rect.y = boxY;
          rect.fills = [{ type: 'SOLID', color: {r: 0.03, g: 0.03, b: 0.03} }];
          
          if (item.image) {
            try {
              const imageBytes = figma.base64Decode(item.image);
              const figmaImage = figma.createImage(imageBytes);
              rect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
              rect.strokes = [{ type: 'SOLID', color: borderDim }];
              rect.strokeWeight = 1;
            } catch (e) {
              console.log("Error loading image", e);
            }
          } else {
            rect.strokes = [{ type: 'SOLID', color: borderDim }];
            rect.strokeWeight = 1;
            rect.dashPattern = [5, 5];
          }

        }
      }
      else if (slide.type === 'workflow_slide') {
        const titleNode = createTextWrap(slide.title, 42, accentYellow, 1600, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        let startY = 350;

        if (slide.body) {
          const bodyNode = createTextWrap(slide.body, 16, { r: 0, g: 1, b: 102/255 }, 1600);
          frame.appendChild(bodyNode);
          bodyNode.x = 80;
          bodyNode.y = startY;
          startY = bodyNode.y + bodyNode.height + 40;
        }

        let currentX = 80;
        
        slide.steps.forEach((step: any, index: number) => {
          const box = figma.createRectangle();
          frame.appendChild(box);
          box.resize(300, 200);
          box.x = currentX;
          box.y = startY;
          box.fills = [{ type: 'SOLID', color: {r: 0.05, g: 0.05, b: 0.05} }];
          box.strokes = [{ type: 'SOLID', color: borderDim }];
          box.strokeWeight = 2;

          const stepTitle = createTextWrap(step.title, 20, accentYellow, 260, true);
          frame.appendChild(stepTitle);
          stepTitle.x = currentX + 20;
          stepTitle.y = startY + 20;

          const stepDesc = createTextWrap(step.desc, 16, textLight, 260, false);
          frame.appendChild(stepDesc);
          stepDesc.x = currentX + 20;
          stepDesc.y = stepTitle.y + stepTitle.height + 15;

          currentX += 300;

          if (index < slide.steps.length - 1) {
            const arrow = figma.createLine();
            frame.appendChild(arrow);
            arrow.x = currentX + 10;
            arrow.y = startY + 100;
            arrow.resize(40, 0);
            arrow.strokes = [{ type: 'SOLID', color: textDim }];
            arrow.strokeWeight = 2;
            arrow.strokeCap = "ARROW_LINES";
            
            currentX += 60;
          }
        });

        if (slide.bottom_body) {
          const bottomBodyNode = createTextWrap(slide.bottom_body, 16, textLight, 1600);
          frame.appendChild(bottomBodyNode);
          bottomBodyNode.x = 80;
          bottomBodyNode.y = startY + 200 + 40;
        }
      }

      generatedNodes.push(frame);
      // Give 200px gap between slides on the Figma Canvas
      xOffset += 2120;
    }

    figma.currentPage.selection = generatedNodes;
    figma.viewport.scrollAndZoomIntoView(generatedNodes);
    figma.notify("✅ Zine Layout Generated!");
  }
};
