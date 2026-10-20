# Third-party source notices

This local implementation incorporates source from Datawhale FunRec:
https://github.com/datawhalechina/fun-rec

Inherited files include the original backend business APIs, offline/online recommendation components, model definitions in `backend/vendor/funrec`, and original frontend browsing/authentication components. CineWeave adds the chat agent, semantic retrieval service, contextual recommendation path, chat UI, and evaluation tooling.

The local source snapshot supplied for this work did not contain a root license file. No license is invented here. Before redistributing inherited code, verify the applicable upstream license and retain all required notices. This implementation task is local; application code is not automatically pushed to the public documentation repository.

BGE-M3 is provided by BAAI; its model card identifies the model license as MIT:
https://huggingface.co/BAAI/bge-m3

MovieLens and enriched movie metadata retain their source-specific terms. Data and model weights are not committed to Git. Existing pretrained recommendation artifacts are reused for engineering integration, not claimed as newly trained CineWeave results.
