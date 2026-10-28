# coding=utf-8
# Lint as: python3
"""The SCROLLS benchmark."""

import json
import os
import datasets

_SCROLLS_CITATION = """
@misc{shaham2022scrolls,
      title={SCROLLS: Standardized CompaRison Over Long Language Sequences}, 
      author={Uri Shaham and Elad Segal and Maor Ivgi and Avia Efrat and Ori Yoran and Adi Haviv and Ankit Gupta and Wenhan Xiong and Mor Geva and Jonathan Berant and Omer Levy},
      year={2022},
      eprint={2201.03533},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
Note that each SCROLLS dataset has its own citation. Please see the source to
get the correct citation for each contained dataset.
"""

_SCROLLS_DESCRIPTION = """
SCROLLS: Standardized CompaRison Over Long Language Sequences.
A suite of natural language datasets that require reasoning over long texts.
https://scrolls-benchmark.com/
"""

_SUMM_SCREEN_DESCRIPTION = """
SummScreenFD (Chen  et al., 2021) is a summarization dataset in the domain of TV shows (e.g. Friends, Game of Thrones).
Given a transcript of a specific episode, the goal is to produce the episode's recap.
The original dataset is divided into two complementary subsets, based on the source of its community contributed transcripts. 
For SCROLLS, we use the ForeverDreaming (FD) subset, as it incorporates 88 different shows, 
making it a more diverse alternative to the TV MegaSite (TMS) subset, which has only 10 shows. 
Community-authored recaps for the ForeverDreaming transcripts were collected from English Wikipedia and TVMaze."""


_QASPER_DESCRIPTION = """
Qasper (Dasigi et al., 2021) is a question answering dataset over NLP papers filtered from the Semantic Scholar Open Research Corpus (S2ORC).
Questions were written by NLP practitioners after reading only the title and abstract of the papers, 
while another set of NLP practitioners annotated the answers given the entire document.
Qasper contains abstractive, extractive, and yes/no questions, as well as unanswerable ones."""


_QMSUM_DESCRIPTION = """
QMSum (Zhong et al., 2021) is a query-based summarization dataset, consisting of 232 meetings transcripts from multiple domains. 
The corpus covers academic group meetings at the International Computer Science Institute and their summaries, industrial product meetings for designing a remote control, 
and committee meetings of the Welsh and Canadian Parliaments, dealing with a variety of public policy issues.
Annotators were tasked with writing queries about the broad contents of the meetings, as well as specific questions about certain topics or decisions, 
while ensuring that the relevant text for answering each query spans at least 200 words or 10 turns."""

_NARRATIVE_QA_DESCRIPTION = """
NarrativeQA (Kočiský et al., 2021) is an established question answering dataset over entire books from Project Gutenberg and movie scripts from different websites.
Annotators were given summaries of the books and scripts obtained from Wikipedia, and asked to generate question-answer pairs, 
resulting in about 30 questions and answers for each of the 1,567 books and scripts.
They were encouraged to use their own words rather then copying, and avoid asking yes/no questions or ones about the cast.
Each question was then answered by an additional annotator, providing each question with two reference answers (unless both answers are identical).."""


_GOV_REPORT_DESCRIPTION = """
GovReport (Huang et al., 2021) is a summarization dataset of reports addressing various national policy issues published by the 
Congressional Research Service and the U.S. Government Accountability Office, where each document is paired with a hand-written executive summary.
The reports and their summaries are longer than their equivalents in other popular long-document summarization datasets; 
for example, GovReport's documents are approximately 1.5 and 2.5 times longer than the documents in Arxiv and PubMed, respectively."""


_CONTRACT_NLI_DESCRIPTION = """
Contract NLI (Koreeda and Manning, 2021) is a natural language inference dataset in the legal domain.
Given a non-disclosure agreement (the premise), the task is to predict whether a particular legal statement (the hypothesis) is entailed, not entailed (neutral), or cannot be entailed (contradiction) from the contract.
The NDAs were manually picked after simple filtering from the Electronic Data Gathering, Analysis, and Retrieval system (EDGAR) and Google.
The dataset contains a total of 607 contracts and 17 unique hypotheses, which were combined to produce the dataset's 10,319 examples."""


_QUALITY_DESCRIPTION = """
QuALITY (Pang et al., 2021) is a multiple-choice question answering dataset over articles and stories sourced from Project Gutenberg, 
the Open American National Corpus, and more.
Experienced writers wrote questions and distractors, and were incentivized to write answerable, unambiguous questions such that in order to correctly answer them, 
human annotators must read large portions of the given document. 
Reference answers were then calculated using the majority vote between of the annotators and writer's answers.
To measure the difficulty of their questions, Pang et al. conducted a speed validation process, 
where another set of annotators were asked to answer questions given only a short period of time to skim through the document.
As a result, 50% of the questions in QuALITY are labeled as hard, i.e. the majority of the annotators in the speed validation setting chose the wrong answer."""


_SUMM_SCREEN_CITATION = r"""
@misc{chen2021summscreen,
      title={SummScreen: A Dataset for Abstractive Screenplay Summarization}, 
      author={Mingda Chen and Zewei Chu and Sam Wiseman and Kevin Gimpel},
      year={2021},
      eprint={2104.07091},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}"""

_QASPER_CITATION = r"""
@inproceedings{dasigi-etal-2021-dataset,
    title = "A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers",
    author = "Dasigi, Pradeep  and
      Lo, Kyle  and
      Beltagy, Iz  and
      Cohan, Arman  and
      Smith, Noah A.  and
      Gardner, Matt",
    booktitle = "Proceedings of the 2021 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies",
    month = jun,
    year = "2021",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.naacl-main.365",
    doi = "10.18653/v1/2021.naacl-main.365",
    pages = "4599--4610",
    abstract = "Readers of academic research papers often read with the goal of answering specific questions. Question Answering systems that can answer those questions can make consumption of the content much more efficient. However, building such tools requires data that reflect the difficulty of the task arising from complex reasoning about claims made in multiple parts of a paper. In contrast, existing information-seeking question answering datasets usually contain questions about generic factoid-type information. We therefore present Qasper, a dataset of 5049 questions over 1585 Natural Language Processing papers. Each question is written by an NLP practitioner who read only the title and abstract of the corresponding paper, and the question seeks information present in the full text. The questions are then answered by a separate set of NLP practitioners who also provide supporting evidence to answers. We find that existing models that do well on other QA tasks do not perform well on answering these questions, underperforming humans by at least 27 F1 points when answering them from entire papers, motivating further research in document-grounded, information-seeking QA, which our dataset is designed to facilitate.",
}"""

_QMSUM_CITATION = r"""@inproceedings{zhong-etal-2021-qmsum,
    title = "{QMS}um: A New Benchmark for Query-based Multi-domain Meeting Summarization",
    author = "Zhong, Ming  and
      Yin, Da  and
      Yu, Tao  and
      Zaidi, Ahmad  and
      Mutuma, Mutethia  and
      Jha, Rahul  and
      Awadallah, Ahmed Hassan  and
      Celikyilmaz, Asli  and
      Liu, Yang  and
      Qiu, Xipeng  and
      Radev, Dragomir",
    booktitle = "Proceedings of the 2021 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies",
    month = jun,
    year = "2021",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.naacl-main.472",
    doi = "10.18653/v1/2021.naacl-main.472",
    pages = "5905--5921",
    abstract = "Meetings are a key component of human collaboration. As increasing numbers of meetings are recorded and transcribed, meeting summaries have become essential to remind those who may or may not have attended the meetings about the key decisions made and the tasks to be completed. However, it is hard to create a single short summary that covers all the content of a long meeting involving multiple people and topics. In order to satisfy the needs of different types of users, we define a new query-based multi-domain meeting summarization task, where models have to select and summarize relevant spans of meetings in response to a query, and we introduce QMSum, a new benchmark for this task. QMSum consists of 1,808 query-summary pairs over 232 meetings in multiple domains. Besides, we investigate a locate-then-summarize method and evaluate a set of strong summarization baselines on the task. Experimental results and manual analysis reveal that QMSum presents significant challenges in long meeting summarization for future research. Dataset is available at \url{https://github.com/Yale-LILY/QMSum}.",
}"""

_NARRATIVE_QA_CITATION = r"""
@article{kovcisky2018narrativeqa,
  title={The narrativeqa reading comprehension challenge},
  author={Ko{\v{c}}isk{\'y}, Tom{\'a}{\v{s}} and Schwarz, Jonathan and Blunsom, Phil and Dyer, Chris and Hermann, Karl Moritz and Melis, G{\'a}bor and Grefenstette, Edward},
  journal={Transactions of the Association for Computational Linguistics},
  volume={6},
  pages={317--328},
  year={2018},
  publisher={MIT Press}
}"""

_GOV_REPORT_CITATION = r"""
@inproceedings{huang-etal-2021-efficient,
    title = "Efficient Attentions for Long Document Summarization",
    author = "Huang, Luyang  and
      Cao, Shuyang  and
      Parulian, Nikolaus  and
      Ji, Heng  and
      Wang, Lu",
    booktitle = "Proceedings of the 2021 Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies",
    month = jun,
    year = "2021",
    address = "Online",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.naacl-main.112",
    doi = "10.18653/v1/2021.naacl-main.112",
    pages = "1419--1436",
    abstract = "The quadratic computational and memory complexities of large Transformers have limited their scalability for long document summarization. In this paper, we propose Hepos, a novel efficient encoder-decoder attention with head-wise positional strides to effectively pinpoint salient information from the source. We further conduct a systematic study of existing efficient self-attentions. Combined with Hepos, we are able to process ten times more tokens than existing models that use full attentions. For evaluation, we present a new dataset, GovReport, with significantly longer documents and summaries. Results show that our models produce significantly higher ROUGE scores than competitive comparisons, including new state-of-the-art results on PubMed. Human evaluation also shows that our models generate more informative summaries with fewer unfaithful errors.",
}"""

_CONTRACT_NLI_CITATION = """\
@inproceedings{koreeda-manning-2021-contractnli,
    title = "ContractNLI: A Dataset for Document-level Natural Language Inference for Contracts",
    author = "Koreeda, Yuta  and
      Manning, Christopher D.",
    booktitle = "Findings of the Association for Computational Linguistics: EMNLP 2021",
    year = "2021",
    publisher = "Association for Computational Linguistics"
}
"""
_QUALITY_CITATION = """\
@article{pang2021quality,
  title={{QuALITY}: Question Answering with Long Input Texts, Yes!},
  author={Pang, Richard Yuanzhe and Parrish, Alicia and Joshi, Nitish and Nangia, Nikita and Phang, Jason and Chen, Angelica and Padmakumar, Vishakh and Ma, Johnny and Thompson, Jana and He, He and Bowman, Samuel R.},
  journal={arXiv preprint arXiv:2112.08608},
  year={2021}
}
"""


class ScrollsConfig(datasets.BuilderConfig):
    """BuilderConfig for SCROLLS."""

    def __init__(self, features, data_url, citation, url, **kwargs):
        """BuilderConfig for SCROLLS.
        Args:
          features: `list[string]`, list of the features that will appear in the
            feature dict. Should not include "label".
          data_url: `string`, url to download the zip file from.
          citation: `string`, citation for the data set.
          url: `string`, url for information about the data set.
          label_classes: `list[string]`, the list of classes for the label if the
            label is present as a string. Non-string labels will be cast to either
            'False' or 'True'.
          **kwargs: keyword arguments forwarded to super.
        """
        super(ScrollsConfig, self).__init__(version=datasets.Version("1.0.0"), **kwargs)
        self.features = features
        self.data_url = data_url
        self.citation = citation
        self.url = url


class QualityConfig(ScrollsConfig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hard_only = False


class Scrolls(datasets.GeneratorBasedBuilder):
    """The SCROLLS benchmark."""

    features = ["id", "pid", "input", "output"]
    DEFAULT_WRITER_BATCH_SIZE = 1000  # because Narrative QA is a rather large dataset
    BUILDER_CONFIGS = [
        ScrollsConfig(
            name="summ_screen_fd",
            description=_SUMM_SCREEN_DESCRIPTION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/summ_screen_fd.zip",
            citation=_SUMM_SCREEN_CITATION,
            url="https://github.com/mingdachen/SummScreen",
        ),
        ScrollsConfig(
            name="qasper",
            description=_QASPER_DESCRIPTION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/qasper.zip",
            citation=_QASPER_CITATION,
            url="https://allenai.org/project/qasper",
        ),
        ScrollsConfig(
            name="qmsum",
            description=_QMSUM_DESCRIPTION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/qmsum.zip",
            citation=_QMSUM_CITATION,
            url="https://github.com/Yale-LILY/QMSum",
        ),
        ScrollsConfig(
            name="narrative_qa",
            description=_NARRATIVE_QA_DESCRIPTION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/narrative_qa.zip",
            citation=_NARRATIVE_QA_CITATION,
            url="https://deepmind.com/research/publications/narrativeqa-reading-comprehension-challenge",
        ),
        ScrollsConfig(
            name="gov_report",
            description=_GOV_REPORT_CITATION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/gov_report.zip",
            citation=_GOV_REPORT_DESCRIPTION,
            url="https://gov-report-data.github.io/",
        ),
        ScrollsConfig(
            name="contract_nli",
            description=_CONTRACT_NLI_DESCRIPTION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/contract_nli.zip",
            citation=_CONTRACT_NLI_CITATION,
            url="https://stanfordnlp.github.io/contract-nli/",
        ),
        QualityConfig(
            name="quality",
            description=_QUALITY_CITATION,
            features=features,
            data_url="https://huggingface.co/datasets/tau/scrolls/resolve/main/quality.zip",
            citation=_QUALITY_DESCRIPTION,
            url="https://github.com/nyu-mll/quality",
        ),
    ]

    def _info(self):
        features = {feature: datasets.Value("string") for feature in self.config.features}

        return datasets.DatasetInfo(
            description=_SCROLLS_DESCRIPTION + self.config.description,
            features=datasets.Features(features),
            homepage=self.config.url,
            citation=self.config.citation + "\n" + _SCROLLS_CITATION,
        )

    def _split_generators(self, dl_manager):
        dl_dir = dl_manager.download_and_extract(self.config.data_url)
        task_name = _get_task_name_from_data_url(self.config.data_url)
        dl_dir = os.path.join(dl_dir, task_name)

        data_files = {} if self.config.data_files is not None else None
        if data_files is not None:
            for split, paths in self.config.data_files.items():
                data_files[split] = paths[0]

        return [
            datasets.SplitGenerator(
                name=datasets.Split.TRAIN,
                gen_kwargs={
                    "data_file": os.path.join(dl_dir, "train.jsonl"),
                    "split": datasets.Split.TRAIN,
                },
            ),
            datasets.SplitGenerator(
                name=datasets.Split.VALIDATION,
                gen_kwargs={
                    "data_file": os.path.join(dl_dir, "validation.jsonl"),
                    "split": datasets.Split.VALIDATION,
                },
            ),
            datasets.SplitGenerator(
                name=datasets.Split.TEST,
                gen_kwargs={
                    "data_file": os.path.join(dl_dir, "test.jsonl") if data_files is None else data_files["test"],
                    "split": datasets.Split.TEST,
                },
            ),
        ]

    def _generate_examples(self, data_file, split):
        with open(data_file, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)

                if self.config.name == "quality":
                    is_hard = row.pop("is_hard", False)
                    if self.config.hard_only and not is_hard:
                        continue

                yield row["pid"], row


def _get_task_name_from_data_url(data_url):
    return data_url.split("/")[-1].split(".")[0]
