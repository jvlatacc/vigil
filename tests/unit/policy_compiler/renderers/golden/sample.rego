# Vigil JIT compiled policy: pol_307d1ed96058623d v1 (content sha256:59465c16c8b96db4d880dde6e166eb53377bc57307801e76924a586fce805029)
# Archetype: workflow wf_hunt_cred_stuffing over 30 days
# Match: data_source in ['okta.system_log', 'splunk']; techniques any_of ['T1110.003', 'T1110.004']; entity-context types all_of ['src_ip', 'user_account']
# Decision: severity=high confidence=0.93 recommended_action=investigate (actions human-only)
# Rendered for OPA (Rego v1) by the Vigil policy compiler — generated artifact, do not edit.

package vigil.compiled_policies

default policy_match := false

policy_match if {
	not workflow_mismatch
	data_source_matches
	techniques_any_of_hit
	type_present_src_ip
	type_present_user_account
}

workflow_mismatch if {
	input.workflow_id != "wf_hunt_cred_stuffing"
}

data_source_matches if {
	input.data_source == "okta.system_log"
}

data_source_matches if {
	input.data_source == "splunk"
}

techniques_any_of_hit if {
	is_object(input.mitre_predictions)
	input.mitre_predictions["T1110.003"]
}

techniques_any_of_hit if {
	is_object(input.mitre_predictions)
	input.mitre_predictions["T1110.004"]
}

type_present_src_ip if {
	is_object(input.entity_context)
	non_empty(input.entity_context["src_ips"])
}

type_present_src_ip if {
	is_object(input.entity_context)
	non_empty(input.entity_context["src_ip"])
}

type_present_user_account if {
	is_object(input.entity_context)
	non_empty(input.entity_context["usernames"])
}

type_present_user_account if {
	is_object(input.entity_context)
	non_empty(input.entity_context["username"])
}

non_empty(value) if {
	is_array(value)
	count(value) > 0
}

non_empty(value) if {
	is_string(value)
	value != ""
}

non_empty(value) if {
	is_object(value)
	count(value) > 0
}
