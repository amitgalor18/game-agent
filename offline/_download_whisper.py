"""Download a faster-whisper model to a directory. Called by download_bundle.sh."""
import os
import sys

def main():
    if len(sys.argv) != 3:
        print("Usage: python _download_whisper.py <output_dir> <model_name>", file=sys.stderr)
        sys.exit(1)
    output_dir = os.path.abspath(sys.argv[1])
    model_name = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)
    from faster_whisper import download_model
    download_model(model_name, output_dir=output_dir)
    print("Saved to", output_dir)

if __name__ == "__main__":
    main()
