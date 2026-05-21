from pathlib import Path

from setuptools import find_packages, setup


def files_under(folder: str, pattern: str = "*") -> list[str]:
    return [str(path) for path in Path(folder).glob(pattern) if path.is_file()]


setup(
    name="oh-my-rtl-claw",
    version="0.1.0",
    description="Multi-agent RTL design orchestrator",
    packages=find_packages(),
    include_package_data=True,
    data_files=[
        ("config", files_under("config", "*.yaml")),
        ("config/prompts", files_under("config/prompts", "*.md")),
        ("locale", files_under("locale", "*.yaml")),
        ("docs/assets", files_under("docs/assets", "*.svg")),
        ("examples", files_under("examples", "*.py")),
    ],
    install_requires=[
        "httpx>=0.27.0",
        "aiohttp>=3.9.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "rich>=13.0.0",
        "click>=8.0.0",
    ],
    entry_points={
        "console_scripts": [
            "oh-my-rtl-claw=oh_my_rtl_claw.main:main",
            "omrc=oh_my_rtl_claw.main:main",
        ],
    },
)
