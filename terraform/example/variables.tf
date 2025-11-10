variable "model_name" {
  type        = string
  default     = null
  description = "Name of an existing model to use. If not provided, a new model will be created."
}

variable "model_owner" {
  type        = string
  default     = "admin"
  description = "Owner of the existing model (used with model_name)."
}

variable "new_model_name" {
  type        = string
  default     = "landscape-charm-build"
  description = "Name for the new model if model_name is not provided."
}

variable "platform" {
  type        = string
  default     = "ubuntu@22.04:amd64"
  description = "The platform to pack the local charm for."
}
