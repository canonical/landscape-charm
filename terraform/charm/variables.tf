# © 2025 Canonical Ltd.

variable "app_name" {
  description = "Name of the application in the Juju model."
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
  default     = "latest-stable/edge"
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
  description = "Revision number of the charm."
  type        = number
  # i.e., latest revision available for the channel
  default  = null
  nullable = true
}

variable "units" {
  description = "Number of units to deploy."
  type        = number
  default     = 1
}
