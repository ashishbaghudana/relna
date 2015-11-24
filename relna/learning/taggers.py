import abc
import re
from nala.learning.taggers import RelationExtractor
from nala.utils.ncbi_utils import GNormPlus
from nala.utils.uniprot_utils import Uniprot
from relna.utils.swissprot_utils import Swissprot
from relna.utils.go_utils import GOTerms
from nala.structures.data import Entity, Relation
from nala.utils import MUT_CLASS_ID, PRO_CLASS_ID, PRO_REL_MUT_CLASS_ID, ENTREZ_GENE_ID, UNIPROT_ID
from nala.learning.taggers import Tagger


class TranscriptionFactorTagger(Tagger):
    """
    Performs tagging for transcription factors in text, using GNormPlus and
    GO Term GO:0003700 or its descendents as the key. Any protein that has this
    GO Term will be automatically tagged as a transcription factor.
    """
    def __init__(self, goterms):
        super().__init__([ENTREZ_GENE_ID, UNIPROT_ID])
        self.transfac_go_terms = self.read_go_terms(goterms)

    def tag(self, dataset, annotated=False, uniprot=False):
        """
        :type dataset: nala.structures.data.Dataset
        :param annotated: if True then saved into annotations otherwise into predicted_annotations
        """
        with GNormPlus() as gnorm:
            for docid, doc in dataset.documents.items():
                if 'Conclusion' in doc.get_text():  # todo check whether this is enough for finding out if full document or not
                    genes = gnorm.get_genes_for_text(doc, docid, postproc=True)
                else:
                    genes = gnorm.get_genes_for_pmid(docid, postproc=True)

                # genes
                # if uniprot normalisation as well then:
                genes_mapping = {}
                if uniprot:
                    with Swissprot() as uprot:
                        list_of_ids = gnorm.uniquify_genes(genes)
                        genes_mapping = uprot.get_uniprotid_for_entrez_geneid(list_of_ids)

                goterms_mapping = {}
                with GOTerms() as go:
                    list_of_ids = self.uniquify_proteins(genes_mapping.values())
                    goterms_mapping = go.get_goterms_for_uniprot_id(list_of_ids)

                last_index = -1
                part_index = 0
                for partid, part in doc.parts.items():
                    last_index = part_index
                    part_index += part.get_size() + 1
                    for gene in genes:
                        if gene[2] in part.text and last_index <= gene[0] < part_index:
                            start = gene[0] - last_index
                            # todo discussion which confidence value for gnormplus because there is no value supplied
                            ann = Entity(class_id=PRO_CLASS_ID, offset=start, text=gene[2], confidence=0.5)
                            try:
                                uniprotids = genes_mapping[gene[3]]
                                for uniprotid in uniprotids:
                                    go_terms = goterms_mapping[uniprotid]
                                    for go_term in go_terms:
                                        if go_term in self.transfac_go_terms:
                                            ann.class_id=MUT_CLASS_ID
                            except KeyError:
                                pass
                            try:
                                norm_dict = {
                                    ENTREZ_GENE_ID: gene[3],
                                    UNIPROT_ID: genes_mapping[gene[3]]
                                }
                            except KeyError:
                                norm_dict = {'EntrezGeneID': gene[3]}

                            norm_string = ''  # todo normalized_text (stemming ... ?)
                            ann.normalisation_dict = norm_dict
                            ann.normalized_text = norm_string
                            if annotated:
                                part.annotations.append(ann)
                            else:
                                part.predicted_annotations.append(ann)

    def read_go_terms(self, file):
        with open(file) as goose:
            return goose.read().splitlines()

    def uniquify_proteins(self, proteins_object):
        """
        :param proteins_object: list(list[str])
        :return: unique list of genes in an array
        """
        return_list = set()
        for obj in proteins_object:
            for protein in obj:
                return_list.add(protein)
        return return_list


class RelnaRelationExtractor(RelationExtractor):
    def __init__(self, entity1_class, entity2_class, rel_type, svmlight):
        super().__init__(entity1_class, entity2_class, rel_type)
        self.svmlight = svmlight
        """an instance of SVMLightTreeKernels"""

    def tag(self, dataset, feature_set):
        self.svmlight.create_input_file(dataset, 'predict', feature_set)
        self.svmlight.tag()
        self.svmlight.read_predictions(dataset)
