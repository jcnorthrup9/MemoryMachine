"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
// --- MEMORY MACHINE DESIGN TOKENS ---
const bgDark = { r: 5 / 255, g: 5 / 255, b: 5 / 255 };
const textLight = { r: 204 / 255, g: 204 / 255, b: 204 / 255 };
const textDim = { r: 136 / 255, g: 136 / 255, b: 136 / 255 };
const accentYellow = { r: 1, g: 244 / 255, b: 202 / 255 };
const borderDim = { r: 34 / 255, g: 34 / 255, b: 34 / 255 };
// --- HELPER FUNCTIONS ---
/**
 * A helper function to create styled text nodes, loading the font if needed.
 */
function createStyledText(text_1, size_1, color_1) {
    return __awaiter(this, arguments, void 0, function* (text, size, color, isBold = false) {
        const node = figma.createText();
        const fontStyle = isBold ? "Bold" : "Regular";
        yield figma.loadFontAsync({ family: "Roboto Mono", style: fontStyle });
        node.fontName = { family: "Roboto Mono", style: fontStyle };
        node.fontSize = size;
        node.fills = [{ type: 'SOLID', color }];
        node.characters = text;
        node.textAutoResize = "HEIGHT";
        return node;
    });
}
/**
 * Finds the current rightmost position of any item on the canvas to avoid overlap.
 */
function getCanvasOffset() {
    let max_x = 0;
    for (const node of figma.currentPage.children) {
        max_x = Math.max(max_x, node.x + node.width);
    }
    return max_x + 200; // Add a 200px gap
}
/**
 * Generic function to generate Figma nodes from a payload object.
 */
function generateFromPayload(payload) {
    return __awaiter(this, void 0, void 0, function* () {
        // --- TASK BOARD GENERATOR ---
        if (msg.type === 'generate-tasks') {
            const tasks = msg.payload;
            let yOffset = 0;
            const cardWidth = 350;
            const cardGap = 20;
            const padding = 20;
            for (const task of tasks) {
                const cardFrame = figma.createFrame();
                cardFrame.name = `Task: ${task.task}`;
                cardFrame.fills = [{ type: 'SOLID', color: bgDark }];
                cardFrame.strokes = [{ type: 'SOLID', color: borderDim }];
                cardFrame.strokeWeight = 1;
                cardFrame.cornerRadius = 8;
                cardFrame.x = xOffset;
                cardFrame.y = yOffset;
                let innerY = padding;
                // Task Title with Checkbox
                const checkbox = task.done ? "☑" : "☐";
                const titleColor = task.done ? textDim : textLight;
                const titleNode = yield createStyledText(`${checkbox} ${task.task}`, 16, titleColor, true);
                titleNode.x = padding;
                titleNode.y = innerY;
                titleNode.resize(cardWidth - padding * 2, titleNode.height);
                cardFrame.appendChild(titleNode);
                innerY += titleNode.height + 10;
                // Priority Status
                if (task.priority) {
                    const priorityNode = yield createStyledText(`Priority: ${task.priority}`, 12, accentYellow);
                    priorityNode.x = padding;
                    priorityNode.y = innerY;
                    cardFrame.appendChild(priorityNode);
                    innerY += priorityNode.height + 15;
                }
                // Description
                if (task.description) {
                    const descNode = yield createStyledText(task.description, 14, textLight);
                    descNode.x = padding;
                    descNode.y = innerY;
                    descNode.resize(cardWidth - padding * 2, descNode.height);
                    cardFrame.appendChild(descNode);
                    innerY += descNode.height;
                }
                cardFrame.resize(cardWidth, innerY + padding);
                generatedNodes.push(cardFrame);
                yOffset += cardFrame.height + cardGap;
            }
            figma.notify("✅ Todo Board Generated!");
        }
        // --- CALENDAR GENERATOR ---
        if (msg.type === 'generate-calendar') {
            const calendarData = msg.payload; // Expects { title: "...", weeks: 4 }
            const masterFrame = figma.createFrame();
            masterFrame.name = calendarData.title || "Visual Calendar";
            masterFrame.fills = []; // Transparent master frame
            masterFrame.x = xOffset;
            masterFrame.y = 0;
            const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
            const dayWidth = 250;
            const dayHeight = 150;
            const headerHeight = 50;
            const gap = 10;
            const numWeeks = calendarData.weeks || 4;
            let currentX = 0;
            let currentY = 0;
            // Create Day Headers
            for (const day of days) {
                const headerNode = yield createStyledText(day, 14, accentYellow, true);
                headerNode.textAlignHorizontal = "CENTER";
                headerNode.resize(dayWidth, headerHeight);
                headerNode.x = currentX;
                headerNode.y = currentY;
                masterFrame.appendChild(headerNode);
                currentX += dayWidth + gap;
            }
            currentY += headerHeight + gap;
            // Create Calendar Grid
            for (let week = 0; week < numWeeks; week++) {
                currentX = 0;
                for (let day = 0; day < 7; day++) {
                    const dayCell = figma.createRectangle();
                    dayCell.name = `W${week + 1}-D${day + 1}`;
                    dayCell.resize(dayWidth, dayHeight);
                    dayCell.x = currentX;
                    dayCell.y = currentY;
                    dayCell.fills = [{ type: 'SOLID', color: bgDark }];
                    dayCell.strokes = [{ type: 'SOLID', color: borderDim }];
                    dayCell.strokeWeight = 1;
                    dayCell.cornerRadius = 4;
                    masterFrame.appendChild(dayCell);
                    // Add date number (example)
                    const dateNum = week * 7 + day + 1;
                    const dateNode = yield createStyledText(dateNum.toString(), 12, textDim);
                    dateNode.x = currentX + 10;
                    dateNode.y = currentY + 10;
                    masterFrame.appendChild(dateNode);
                    currentX += dayWidth + gap;
                }
                currentY += dayHeight + gap;
            }
            masterFrame.resize(currentX - gap, currentY - gap);
            generatedNodes.push(masterFrame);
            figma.notify("✅ Visual Calendar Generated!");
        }
        // --- PROJECT PLAN SLIDE GENERATOR (from the other plugin) ---
        if (payload.slides && payload.slides[0].type === 'project_plan_slide') {
            const slide = payload.slides[0];
            const frame = figma.createFrame();
            frame.name = slide.title || "Project Plan";
            frame.resize(1920, 1080);
            frame.x = xOffset;
            frame.fills = [{ type: 'SOLID', color: bgDark }];
            const titleNode = yield createStyledText(slide.title || " ", 42, accentYellow, true);
            frame.appendChild(titleNode);
            titleNode.x = 80;
            titleNode.y = 40;
            let currentY = titleNode.y + titleNode.height + 60;
            if (slide.weeks) {
                for (const week of slide.weeks) {
                    const weekTitle = yield createStyledText(week.week || " ", 24, accentYellow, true);
                    frame.appendChild(weekTitle);
                    weekTitle.x = 80;
                    weekTitle.y = currentY;
                    currentY += weekTitle.height + 20;
                    if (week.tasks) {
                        for (const task of week.tasks) {
                            const checkbox = task.done ? "☑" : "☐";
                            const taskColor = task.done ? textDim : textLight;
                            const taskText = `${checkbox} ${task.task}`;
                            const taskNode = yield createStyledText(taskText, 18, taskColor);
                            frame.appendChild(taskNode);
                            taskNode.x = 100;
                            taskNode.y = currentY;
                            currentY += taskNode.height + 10;
                        }
                    }
                    currentY += 40;
                }
            }
            frame.resize(1920, currentY);
            generatedNodes.push(frame);
            figma.notify("✅ Project Plan Generated!");
        }
        // --- FINALIZATION ---
        if (generatedNodes.length > 0) {
            // Group all generated nodes for easy selection
            const group = figma.group(generatedNodes, figma.currentPage);
            group.name = "Memory Machine Task Output";
            // Select and zoom to the new content
            figma.currentPage.selection = [group];
            figma.viewport.scrollAndZoomIntoView([group]);
        }
        // Close the plugin if you want, or leave it open
        // figma.closePlugin();
    });
}
/**
 * Main plugin execution function. Runs immediately when the plugin is launched.
 */
function main() {
    return __awaiter(this, void 0, void 0, function* () {
        // Define the absolute path to the JSON file to be loaded.
        const filePath = "d:\\MemoryMachine\\data\\figma_plan_payload.json";
        try {
            // Use Figma's fileSystem API to get a handle to the file.
            const file = yield figma.fs.getFileHandle(filePath);
            if (!file) {
                throw new Error("File handle could not be obtained.");
            }
            // Read the file content as a string.
            const content = yield file.readTextAsync();
            const payload = JSON.parse(content);
            // Pass the parsed payload to the generation logic.
            yield generateFromPayload(payload);
        }
        catch (e) {
            // If anything goes wrong (file not found, invalid JSON), notify the user.
            figma.notify(`❌ Error: ${e.message}`, { error: true });
        }
        finally {
            // Always close the plugin after it runs.
            figma.closePlugin();
        }
    });
}
// Start the plugin's main function.
main();
