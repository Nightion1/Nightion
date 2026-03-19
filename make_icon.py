from PIL import Image
import sys
import os

def convert_to_ico(input_path):
    if not os.path.exists(input_path):
        print(f"Error: Could not find file '{input_path}'")
        return

    output_path = "NightionFox.ico"
    
    try:
        # Open the image
        img = Image.open(input_path)
        
        # Ensure it has an alpha channel for transparency
        img = img.convert("RGBA")
        
        # Save as a multi-resolution ICO file
        img.save(output_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
        
        print(f"\n==========================================")
        print(f"✅ Success! Icon created: {os.path.abspath(output_path)}")
        print(f"==========================================\n")
        print(f"You can now right-click your Nightion shortcut -> Properties -> Change Icon -> Browse to this file!")
        
    except Exception as e:
        print(f"Error generating icon: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_icon.py <path_to_your_image>")
        print("Example: python make_icon.py C:\\Users\\Lenovo\\Downloads\\fox.png")
    else:
        convert_to_ico(sys.argv[1])
