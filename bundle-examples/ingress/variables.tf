variable "model_uuid" {
  type = string
}

variable "haproxy_hostname" {
  type    = string
  default = "haproxy.internal"
}

variable "machine" {
    type = string
    default = "0"
}

variable "twisted_workers" {
  type    = number
  default = 2
}
