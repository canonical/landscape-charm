# © 2025 Canonical Ltd.

variable "app_name" {
  description = "Name of the application (charm) in the Juju model."
  type        = string
  default     = "landscape-server"
}

variable "base" {
  description = "The operating system on which to deploy."
  type        = string
  default     = "ubuntu@22.04"
}

variable "channel" {
  description = "The channel to use when deploying a charm."
  type        = string
  default     = "25.10/edge"
}

variable "config" {
  description = "Application config. Details about available options can be found at https://charmhub.io/landscape-server/configurations."
  type        = map(string)
  default     = {}
}

variable "constraints" {
  description = "Juju constraints to apply for this application."
  type        = string
  default     = "arch=amd64"
}

variable "model" {
  description = "Reference to a `juju_model`."
  type        = string
}

variable "revision" {
  description = "Revision number of this charm."
  type        = number
  # latest
  default     = null
}

variable "units" {
  description = "Number of units to deploy for this charm."
  type        = number
  default     = 1
}
