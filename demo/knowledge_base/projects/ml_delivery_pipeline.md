# Project: ML Model Delivery Pipeline (fictional)

A CI/CD pipeline for machine-learning models. Each training run is tracked in MLflow; a GitHub
Actions workflow validates metrics against the current production model, builds a Docker image
and deploys it to a Kubernetes serving layer with a canary rollout.

Demonstrates MLOps practices: model versioning, automated evaluation gates, reproducible builds
and rollback.

Technologies: Python, MLflow, Docker, Kubernetes, GitHub Actions.
