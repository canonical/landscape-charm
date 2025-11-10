variable "model_name" {
  type        = string
  description = "Name for the new model."
}

variable "app_name" {
  type        = string
  default     = "landscape-server"
  description = "Name of the application to refresh with the local charm."
}

variable "platform" {
  type        = string
  default     = "ubuntu@22.04:amd64"
  description = "The platform to pack the local charm for."
}
