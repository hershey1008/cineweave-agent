# Third-party source and media notices

## Datawhale FunRec

Source: https://github.com/datawhalechina/fun-rec

Upstream attribution: Datawhale FunRec contributors. The upstream README, verified on 2026-10-20, declares CC BY-NC-SA 4.0 under its LICENSE heading:
https://github.com/datawhalechina/fun-rec#license

The supplied source snapshot did not include a standalone root license file. The repository-level README declaration is retained here; the canonical license text is included in `licenses/CC-BY-NC-SA-4.0.txt`. No MIT or Apache license is substituted for inherited code.

Inherited components include backend business APIs, authentication, offline/online recommendation components, model definitions under `backend/vendor/funrec`, and frontend browsing/authentication components. CineWeave adds the chat agent, semantic retrieval, contextual recommendation path, chat UI, state consistency, error handling, tests and presentation tooling. See `docs/CONTRIBUTIONS.md` for modifications. No upstream endorsement is implied.

## BGE-M3

BAAI model card: https://huggingface.co/BAAI/bge-m3

Model card identifies MIT licensing. We do not bundle its weights in Git; the downloader retrieves the pinned official revision and verifies the binary digest. Its terms remain separate from the application's adaptation license.

## MovieLens and enriched movie information

MovieLens-1M: https://grouplens.org/datasets/movielens/1m/
Terms: https://files.grouplens.org/datasets/movielens/ml-1m-README.txt

MovieLens explicitly requires separate permission for dataset redistribution and commercial use. This repository does not distribute the raw dataset, enriched pickle files, user rating records or pretrained artifacts. Users prepare their own permitted inputs. The provenance of every enriched description, poster and external entity mapping has not been established; file presence or type filtering is not a rights or factual audit.

Demonstration screenshots/video show the local application with movie artwork and short factual metadata for project explanation. Those third-party images and descriptions are not relicensed as CineWeave assets or offered as a data collection. No rights to reuse movie artwork are granted by the repository LICENSE.

## Software dependencies and generated presentation

Dependencies such as TensorFlow, PyTorch, Vue, FastAPI and their transitive packages retain their individual licenses. They are installed through package managers or container builds, not relicensed here.

The presentation uses actual local application screenshots and locally synthesized Microsoft Huihui narration. Requests were sent to the user's configured LLM; waiting time is omitted in the edited presentation. There is no impersonation, music track, fabricated ranking metric or claim of an unedited screen recording.
