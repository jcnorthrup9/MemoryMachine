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
    const bgColor = { r: 244/255, g: 243/255, b: 236/255 }; // #f4f3ec
    const textColor = { r: 8/255, g: 6/255, b: 13/255 }; // #08060d
    const textDim = { r: 107/255, g: 99/255, b: 117/255 }; // #6b6375
    const borderDim = { r: 229/255, g: 228/255, b: 231/255 }; // #e5e4e7
    const bgLight = { r: 250/255, g: 250/255, b: 248/255 }; // #fafaf8

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
      frame.fills = [{ type: 'SOLID', color: bgColor }];
      
      if (slide.type === 'title_slide') {
        const titleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const subNode = createTextWrap(slide.subtitle, 24, textDim, 800);
        frame.appendChild(subNode);
        subNode.x = 80;
        subNode.y = titleNode.y + titleNode.height + 20;

        if (slide.body) {
          const bodyNode = createTextWrap(slide.body, 16, textDim, 800);
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
        const titleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body, 16, textDim, 800);
        frame.appendChild(bodyNode);
        bodyNode.x = 80;
        bodyNode.y = 250;
      }
      else if (slide.type === 'text_and_mermaid_slide') {
        const titleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body || " ", 16, textDim, 800);
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
        rect.fills = [{ type: 'SOLID', color: bgLight }];
        rect.strokes = [{ type: 'SOLID', color: borderDim }];
        rect.strokeWeight = 1;

        const codeNode = createTextWrap(slide.mermaid_code, 12, textDim, 760);
        frame.appendChild(codeNode);
        codeNode.x = 1060;
        codeNode.y = rect.y + 20;
      }
      else if (slide.type === 'text_and_image_slide') {
        const titleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const bodyNode = createTextWrap(slide.body, 16, textDim, 800);
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
            rect.fills = [{ type: 'SOLID', color: bgLight }];

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
        const titleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        const leftTitle = createTextWrap(slide.left_title, 20, textDim, 800, true);
        frame.appendChild(leftTitle);
        leftTitle.x = 80;
        leftTitle.y = titleNode.y + titleNode.height + 15;

        const leftBody = createTextWrap(slide.left_body, 16, textDim, 800);
        frame.appendChild(leftBody);
        leftBody.x = 80;
        leftBody.y = 250;

        const rightTitle = createTextWrap(slide.right_title, 20, textDim, 800, true);
        frame.appendChild(rightTitle);
        rightTitle.x = 1040;
        rightTitle.y = titleNode.y + titleNode.height + 15;

        const rightBody = createTextWrap(slide.right_body, 16, textColor, 800);
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
        const mainTitleNode = createTextWrap(slide.title, 42, textColor, 800, true, true);
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
          rect.fills = [{ type: 'SOLID', color: bgLight }];
          
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
          rect.fills = [{ type: 'SOLID', color: bgLight }];
          
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
        const titleNode = createTextWrap(slide.title, 42, textColor, 1600, true, true);
        frame.appendChild(titleNode);
        titleNode.x = 80;
        titleNode.y = 40;

        let startY = 350;

        if (slide.body) {
          const bodyNode = createTextWrap(slide.body, 16, textColor, 1600);
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
          box.fills = [{ type: 'SOLID', color: bgLight }];
          box.strokes = [{ type: 'SOLID', color: borderDim }];
          box.strokeWeight = 2;

          const stepTitle = createTextWrap(step.title, 20, textColor, 260, true);
          frame.appendChild(stepTitle);
          stepTitle.x = currentX + 20;
          stepTitle.y = startY + 20;

          const stepDesc = createTextWrap(step.desc, 16, textDim, 260, false);
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
          const bottomBodyNode = createTextWrap(slide.bottom_body, 16, textDim, 1600);
          frame.appendChild(bottomBodyNode);
          bottomBodyNode.x = 80;
          bottomBodyNode.y = startY + 200 + 40;
        }
      }
      else if (slide.type === 'phase_grid_slide') {
        const titleNode = createTextWrap(slide.title, 42, textColor, 1800, true, true);
        titleNode.textAlignHorizontal = "CENTER";
        frame.appendChild(titleNode);
        titleNode.x = 60;
        titleNode.y = 40;

        const cols = slide.columns || [];
        const totalCols = cols.length;
        const margin = 60;
        const colGap = 20;
        const colWidth = (1920 - (margin * 2) - (colGap * (totalCols - 1))) / Math.max(1, totalCols);
        const colHeight = 880;
        const startY = 140;

        cols.forEach((col: any, cIndex: number) => {
          const colX = margin + cIndex * (colWidth + colGap);

          const colBg = figma.createRectangle();
          frame.appendChild(colBg);
          colBg.resize(colWidth, colHeight);
          colBg.x = colX;
          colBg.y = startY;
          colBg.fills = [{ type: 'SOLID', color: bgLight }];
          colBg.strokes = [{ type: 'SOLID', color: borderDim }];
          colBg.strokeWeight = 1;

          const colTitle = createTextWrap(col.title, 20, textColor, colWidth - 40, true);
          colTitle.textAlignHorizontal = "CENTER";
          frame.appendChild(colTitle);
          colTitle.x = colX + 20;
          colTitle.y = startY + 20;

          const items = col.items || [];
          const itemsStartY = startY + 80;
          const itemGap = 20;
          const totalItemHeight = colHeight - 80 - 20; 
          const rowHeight = (totalItemHeight - (itemGap * (items.length - 1))) / Math.max(1, items.length);

          items.forEach((item: any, rIndex: number) => {
            const itemY = itemsStartY + rIndex * (rowHeight + itemGap);
            const hasText = !!(item.desc || item.binary);

            const imgRect = figma.createRectangle();
            frame.appendChild(imgRect);

            let imgWidth = colWidth - 40;
            if (hasText) {
              const iFlex = parseFloat(slide.img_flex || "1");
              const tFlex = parseFloat(slide.text_flex || "1.5");
              imgWidth = (colWidth - 40 - 15) * (iFlex / (iFlex + tFlex));
            }

            imgRect.resize(imgWidth, rowHeight);
            imgRect.x = colX + 20;
            imgRect.y = itemY;
            imgRect.fills = [{ type: 'SOLID', color: bgColor }];

            if (item.image && item.image.image) {
              try {
                const imageBytes = figma.base64Decode(item.image.image);
                const figmaImage = figma.createImage(imageBytes);
                imgRect.fills = [{ type: 'IMAGE', scaleMode: 'FILL', imageHash: figmaImage.hash }];
                imgRect.strokes = [{ type: 'SOLID', color: borderDim }];
                imgRect.strokeWeight = 1;
              } catch (e) { console.log("Error loading phase image", e); }
            } else {
              imgRect.strokes = [{ type: 'SOLID', color: borderDim }];
              imgRect.strokeWeight = 1;
              imgRect.dashPattern = [5, 5];
            }

            if (hasText) {
              const textX = imgRect.x + imgWidth + 15;
              const textWidth = colWidth - 40 - imgWidth - 15;
              
              if (item.desc) {
                const descNode = createTextWrap(item.desc, 16, textDim, textWidth);
                frame.appendChild(descNode);
                descNode.x = textX;
                descNode.y = itemY;

                if (item.binary) {
                  const binNode = createTextWrap(item.binary, 10, { r: 156/255, g: 163/255, b: 175/255 }, textWidth);
                  frame.appendChild(binNode);
                  binNode.x = textX;
                  binNode.y = descNode.y + descNode.height + 8;
                }
              }
            }
          });
        });
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
