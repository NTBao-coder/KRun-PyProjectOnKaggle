import json
from pathlib import Path

import torch


def main() -> None:
    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU"
    result = {
        "cuda_available": cuda_available,
        "device": device_name,
        "pytorch_version": torch.__version__,
    }

    print(json.dumps(result, indent=2))
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    (output_dir / "system.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

