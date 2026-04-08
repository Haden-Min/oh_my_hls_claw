from setuptools import find_packages, setup


setup(
    name="oh-my-hls-claw",
    version="0.1.0",
    description="Multi-agent digital system design orchestrator",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "httpx>=0.27.0",
        "aiohttp>=3.9.0",
        "pyyaml>=6.0",
        "python-dotenv>=1.0.0",
        "rich>=13.0.0",
        "click>=8.0.0",
    ],
)
