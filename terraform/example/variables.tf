variable "model_name" {
  type        = string
  description = "Name for the new model (resource)."
}

variable "platform" {
  type        = string
  default     = "ubuntu@22.04:amd64"
  description = "The platform to pack the local charm for."
}
