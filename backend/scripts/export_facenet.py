"""Run in the separate export environment documented in docs/MODELS.md."""
import argparse
from pathlib import Path

import torch
from facenet_pytorch import InceptionResnetV1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("weights/facenet.ts"))
    args = parser.parse_args()
    # Downloads the upstream VGGFace2 checkpoint on this explicit export step.
    model = InceptionResnetV1(pretrained="vggface2").eval().cpu()
    example = torch.randn(1, 3, 160, 160)
    with torch.inference_mode():
        exported = torch.jit.trace(model, example)
        torch.testing.assert_close(model(example), exported(example))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    exported.save(str(args.output))
    print(f"Saved 512-dimensional FaceNet adapter to {args.output}")


if __name__ == "__main__":
    main()

