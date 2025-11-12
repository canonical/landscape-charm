plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

rule "terraform_module_pinned_source" {
  enabled = false
}
