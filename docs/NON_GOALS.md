# Dataset Forge -- Non-Goals

Dataset Forge is a curation workstation, not a general dataset-production
pipeline.

## Not Part Of The Product

- modifying, moving, renaming, deleting, or quarantining source files;
- applying preview candidates to source datasets;
- exporting an improved or trainer-ready dataset;
- automatic cleanup, repair, restoration, enhancement, denoising, or upscaling;
- caption generation, rewriting, prompt optimization, or semantic scoring;
- model training or training-parameter advice;
- quality grades, readiness scores, or automatic pass/fail judgments;
- hosted review, databases, accounts, or cloud synchronization;
- live Krea or ComfyUI integrations;
- plugin discovery or user-installed execution code;
- semantic image search, face recognition, or style matching.

## Preview Generation Is Not Dataset Modification

LOCAL_CLASSICAL may generate a disposable candidate under
`inspect_output/preview_artifacts/`. It never overwrites or replaces a source
image, and approval never applies it.

## Why These Boundaries Exist

The product earns trust through evidence, reproducibility, clear human
decisions, and a small write surface. Features that silently act on source
datasets would weaken those guarantees and change the product category.
