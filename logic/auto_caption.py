import os
from PIL import Image
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration

# --- CONFIGURATION ---
IMAGE_DIRECTORY = r"D:\MemoryMachine\archive\reference_images"
BATCH_SIZE = 8

def get_device():
    """Checks for CUDA-enabled GPU for faster processing."""
    if torch.cuda.is_available():
        print("✅ CUDA is available. Using GPU for captioning.")
        return "cuda"
    else:
        print("⚠️ CUDA not found. Using CPU. This will be much slower.")
        return "cpu"

def generate_captions():
    """
    Finds all images in the target directory without captions and generates them
    in batches using the Salesforce BLIP model.
    """
    device = get_device()
    
    # Load the pre-trained image captioning model from Hugging Face
    print("\nLoading BLIP model... (This may take a moment on first run)")
    processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
    model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large").to(device)
    print("✅ Model loaded.")

    # First, collect all images that need captions
    images_to_process = []
    for root, _, files in os.walk(IMAGE_DIRECTORY):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                image_path = os.path.join(root, file)
                caption_path = os.path.splitext(image_path)[0] + ".txt"
                if not os.path.exists(caption_path):
                    images_to_process.append(image_path)

    if not images_to_process:
        print("\n✅ All images have existing captions. Nothing to do.")
        return

    print(f"\n🔎 Found {len(images_to_process)} image(s) to caption.")

    # Process in batches for significantly faster performance
    for i in range(0, len(images_to_process), BATCH_SIZE):
        batch_paths = images_to_process[i:i+BATCH_SIZE]
        raw_images = []
        valid_paths = []

        print(f"\n--- Processing Batch {i//BATCH_SIZE + 1}/{(len(images_to_process) + BATCH_SIZE - 1) // BATCH_SIZE} ---")
        for image_path in batch_paths:
            try:
                raw_images.append(Image.open(image_path).convert('RGB'))
                valid_paths.append(image_path)
            except Exception as e:
                print(f"❌ Error loading {os.path.basename(image_path)}: {e}")

        if not raw_images:
            continue

        # Generate captions for the entire batch at once
        inputs = processor(raw_images, return_tensors="pt").to(device)
        out = model.generate(**inputs, max_new_tokens=50)
        captions = processor.batch_decode(out, skip_special_tokens=True)

        for path, caption in zip(valid_paths, captions):
            caption_path = os.path.splitext(path)[0] + ".txt"
            with open(caption_path, "w", encoding="utf-8") as f:
                f.write(caption)
            print(f"   -> ✅ Saved for {os.path.basename(path)}: '{caption}'")

if __name__ == "__main__":
    generate_captions()