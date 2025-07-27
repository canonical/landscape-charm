# © 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Name of the application in the Juju model."
  type        = string
  default     = "landscape-server"
}

variable "channel" {
  description = "The channel to use when deploying a charm."
  type        = string
  default     = "latest-stable/edge"
}

variable "config" {
  description = "Application config. Details about available options can be found at https://charmhub.io/landscape-server/configurations?channel=latest-stable/edge."
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
  default     = ""
}

variable "resources" {
  description = "Resources to use with the application. Details about available options can be found at https://charmhub.io/landscape-server/configurations."
  type        = map(string)
  default     = {}
}

variable "revision" {
  description = "Revision number of the charm"
  type        = number
  default     = null
}

variable "base" {
  description = "The operating system on which to deploy"
  type        = string
  default     = "ubuntu@22.04"
}

variable "units" {
  description = "Number of units to deploy"
  type        = number
  default     = 1
}
