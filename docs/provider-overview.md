# Provider Overview

Provider descriptors explain capabilities. A descriptor does not imply that a
provider is installed, connected, or executable.

## Current Providers

| Provider type | Product status | Meaning |
|---|---|---|
| `LOCAL_CLASSICAL` | Implemented for isolated candidate generation | Deterministic Pillow/NumPy preview generation for two supported operations. |
| `MANUAL` | Manual import workflow available | Records and displays a candidate created outside Dataset Forge. |
| `COMFYUI` | Descriptor only | No integration, networking, workflow execution, or subprocess support. |
| `KREA` | Descriptor only | No integration, API client, credentials, or networking. |
| `UNKNOWN` | Fallback descriptor | Represents an unspecified or unsupported planning provider. |

## Capability Matching

Matching compares a planning operation's required capabilities with static
descriptor metadata. Results are deterministic and do not inspect the machine,
discover plugins, contact services, or test provider availability.

## LOCAL_CLASSICAL Boundary

LOCAL_CLASSICAL reads one source image and writes one candidate into the
isolated preview workspace. It:

- supports `REDUCE_HALO` and `REDUCE_ENCODING_ARTIFACTS` only;
- records provider version, operation, parameters, hashes, and warnings;
- uses no randomness, networking, subprocesses, ML, or generative AI;
- never overwrites a source image or applies the result to a dataset.

## Execution Policy

The provider contract requires source writes and source overwrite to remain
forbidden, isolated output and provenance to be present, and human approval to
remain explicit. Dataset-level improvement execution is unavailable.

