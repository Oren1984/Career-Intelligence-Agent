# Project: Self-Service Kubernetes Platform (fictional)

Built an internal developer platform on Amazon EKS. Product teams describe a service in a short
YAML file; a pipeline renders Helm charts, provisions IAM roles with Terraform and syncs the
release with ArgoCD.

Results: deployment requests no longer need a ticket, new services go live in under an hour,
and every service ships with dashboards and alerts by default.

Technologies: Kubernetes, Helm, Terraform, ArgoCD, AWS IAM, GitHub Actions.
