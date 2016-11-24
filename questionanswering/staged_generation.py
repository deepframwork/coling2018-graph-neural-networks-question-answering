import copy
import nltk
from wikidata_access import *
from evaluation import *
from webquestions_io import *
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def get_available_expansions(g):
    """
    Get a list of methods that can be applied on the given graph to expand its denotation.

    :param g: a graph object
    :return: list of methods that take graph as an only argument
    >>> get_available_expansions({'edgeSet':[]})
    []
    >>> hop_up in get_available_expansions({'edgeSet':[{'left':[0], 'right':[2,3]}]})
    True
    """
    if len(g['edgeSet']) > 0 and 'hopUp' not in g['edgeSet'][-1]:
        return [hop_up]
    return []


def get_available_restrictions(g):
    """
    Get a list of methods that can be applied on the given graph to expand restrict denotation.

    :param g: a graph object
    :return: list of methods that take graph as an only argument
    >>> get_available_restrictions({'entities':[], 'edgeSet':[{},{}]})
    []
    >>> add_entity_and_relation in get_available_restrictions({'entities':[[2,3]]})
    True
    """
    if len(g['entities']) > 0:
        return [add_entity_and_relation]
    return []


def remove_token_from_entity(g):
    """

    :param g:
    :return:
    >>> remove_token_from_entity({'edgeSet': [], 'entities': [[4, 5, 6]], 'tokens': ['what', 'country', 'is', 'the', 'grand', 'bahama', 'island', 'in', '?']})
    []
    >>> len(remove_token_from_entity({'edgeSet': [{'left':[0], 'right':[4,5,6]}], 'entities': [], 'tokens': ['what', 'country', 'is', 'the', 'grand', 'bahama', 'island', 'in', '?']}))
    5
    """
    if len(g.get('edgeSet',[])) == 0 or len(g['edgeSet'][0]['right']) < 2:
        return []
    new_graphs = []
    right_entity = g['edgeSet'][0]['right']
    for i in range(1, len(right_entity)):
        for new_entity in list(nltk.ngrams(right_entity, i)):
            new_g = {"tokens": g['tokens'], 'edgeSet': copy.deepcopy(g['edgeSet']), 'entities': g.get('entities', [])}
            new_g['edgeSet'][0]['right'] = list(new_entity)
            new_graphs.append(new_g)
    return new_graphs


def hop_up(g):
    if len(g['edgeSet']) == 0:
        return []
    new_g = {"tokens": g['tokens'], 'edgeSet': copy.deepcopy(g['edgeSet']), 'entities': g.get('entities', [])}
    new_g['edgeSet'][-1]['hopUp'] = 1
    return [new_g]


def add_entity_and_relation(g):
    new_g = {"tokens": g['tokens'], 'edgeSet': copy.deepcopy(g.get('edgeSet', [])), 'entities': g.get('entities', [])}
    entities_left = g['entities']

    if len(entities_left) == 0:
        return []

    entity = entities_left[0]
    new_edge = {'left': [0], 'right': entity}
    new_g['edgeSet'].append(new_edge)

    new_g['entities'] = entities_left[1:] if len(entities_left) > 1 else []
    return [new_g]

# TODO: Add argmax and argmin
EXPAND_ACTIONS = [hop_up, remove_token_from_entity]
RESTRICT_ACTIONS = [add_entity_and_relation]


def expand(g):
    """
    Expand the coverage of the given graph by constructing version that has more possible/other denotations.

    :param g: dict object representing the graph with "edgeSet" and "entities"
    :return: a list of new graphs that are modified copies
    >>> expand({"tokens": ['Who', 'is', 'Barack', 'Obama', '?'], "entities":[[2, 3]]})
    []
    >>> expand({"tokens": ['Who', 'is', 'Barack', 'Obama', '?'], "edgeSet":[{"left":[0], "right":[2,3]}]}) == [{'tokens': ['Who', 'is', 'Barack', 'Obama', '?'], 'entities':[], 'edgeSet': [{'left': [0], 'hopUp': 1, 'right': [2, 3]}]}]
    True
    """
    if "edgeSet" not in g:
        return []
    available_expansions = get_available_expansions(g)
    return_graphs = [el for f in available_expansions for el in f(g)]
    return return_graphs


def restrict(g):
    """
    Restrict the set of possible graph denotations by adding new constraints that should be fullfilled by the linking.

    :param g: dict object representing the graph with "edgeSet" and "entities"
    :return: a list of new graphs that are modified copies
    >>> restrict({"tokens": ['Who', 'is', 'Barack', 'Obama', '?'], "entities":[[2, 3]]}) == [{'edgeSet': [{'left': [0], 'right': [2, 3]}], 'entities': [], 'tokens': ['Who', 'is', 'Barack', 'Obama', '?']}]
    True
    >>> restrict({"tokens": ['Who', 'is', 'Barack', 'Obama', '?'], "edgeSet":[{"left":[0], "right":[2,3]}]})
    []
    """
    if "entities" not in g:
        return []
    available_restrictions = get_available_restrictions(g)
    return_graphs = [el for f in available_restrictions for el in f(g)]
    return return_graphs


def generate_with_gold(ungrounded_graph, question_obj):
    """
    Generate all possible groundings that produce positive f-score starting with the given ungrounded graph and
    using expand and restrict operations on its denotation.

    :param ungrounded_graph: the starting graph that should contain a list of tokens and a list of entities
    :param question_obj: a WebQuestions question encoded as a dictionary
    :return: a list of generated grounded graphs
    """
    pool = [(ungrounded_graph, (0.0, 0.0, 0.0), [])]  # pool of possible parses
    generated_graphs = []
    gold_answers = [e.lower() for e in get_answers_from_question(question_obj)]

    while len(pool) > 0:
        g = pool.pop()
        logger.debug("Pool length: {}, Graph: {}".format(len(pool), g))
        if g[2] < 0.5:
            logger.debug("Restricting")
            suggested_graphs = restrict(g[0])
            logger.debug("Suggested graphs: {}".format(suggested_graphs))
            chosen_graphs = ground_with_gold(suggested_graphs, gold_answers)
            if len(chosen_graphs) == 0:
                logger.debug("Expanding")
                suggested_graphs = [e_g for s_g in suggested_graphs for e_g in expand(s_g)]
                logger.debug("Graph: {}".format(suggested_graphs))
                chosen_graphs = ground_with_gold(suggested_graphs, gold_answers)
            if len(chosen_graphs) > 0:
                logger.debug("Extending the pool.")
                pool.extend(chosen_graphs)
            else:
                logger.debug("Extending the generated graph set.")
                generated_graphs.append(g)
        else:
            logger.debug("Extending the generated graph set.")
            generated_graphs.append(g)

    return generated_graphs


def ground_with_gold(input_graphs, gold_answers):
    """
    For each graph among the suggested_graphs find its groundings in the WikiData, then evaluate each suggested graph
    with each of its possible groundings and compare the denotations with the answers embedded in the question_obj.
    Return all groundings that produce an f-score > 0.0

    :param input_graphs: a list of ungrounded graphs
    :param gold_answers: a set of gold answers
    :return: a list of graph groundings
    """
    grounded_graphs = [apply_grounding(s_g, p) for s_g in input_graphs for p in
                       query_wikidata(graph_to_query(s_g))]
    logger.debug("Number of possible groundings: {}".format(len(grounded_graphs)))
    logger.debug("First one: {}".format(grounded_graphs[:1]))
    retrieved_answers = [query_wikidata(graph_to_query(s_g, return_var_values=True)) for s_g in grounded_graphs]
    logger.debug(
        "Number of retrieved answer sets: {}. Example: {}".format(len(retrieved_answers), retrieved_answers[:1]))
    retrieved_answers = [map_query_results(answer_set) for answer_set in retrieved_answers]

    evaluation_results = [retrieval_prec_rec_f1(gold_answers, retrieved_answers[i]) for i in
                          range(len(grounded_graphs))]
    chosen_graphs = [(grounded_graphs[i], evaluation_results[i], retrieved_answers[i])
                     for i in range(len(grounded_graphs)) if evaluation_results[i][2] > 0.0]
    logger.debug("Number of chosen groundings: {}".format(len(chosen_graphs)))
    return chosen_graphs


def apply_grounding(g, grounding):
    """
    Given a grounding obtained from WikiData apply it to the graph.
    Note: that the variable names returned by WikiData are important as they encode some grounding features.

    :param g: a single ungrounded graph
    :param grounding: a dictionary representing the grounding of relations and variables
    :return: a grounded graph
    >>> apply_grounding({'edgeSet':[{}]}, {'r0d':'P31v'}) == {'edgeSet': [{'type': 'direct', 'kbID': 'P31v'}]}
    True
    >>> apply_grounding({'edgeSet':[{}]}, {'r0v':'P31v'}) == {'edgeSet': [{'type': 'v-structure', 'kbID': 'P31v'}]}
    True
    >>> apply_grounding({'edgeSet':[{}, {}]}, {'r1d':'P39v', 'r0v':'P31v', 'e20': 'Q18'}) == {'edgeSet': [{'type': 'v-structure', 'kbID': 'P31v', 'rightkbID': 'Q18'}, {'type': 'direct', 'kbID': 'P39v'}]}
    True
    >>> apply_grounding({'edgeSet':[]}, {})
    {'edgeSet': []}
    """
    grounded = copy.deepcopy(g)
    for i, edge in enumerate(grounded.get('edgeSet', [])):
        if "e2" + str(i) in grounding:
            edge['rightkbID'] = grounding["e2" + str(i)]
        if "r{}d".format(i) in grounding:
            edge['kbID'] = grounding["r{}d".format(i)]
            edge['type'] = 'direct'
        elif "r{}r".format(i) in grounding:
            edge['kbID'] = grounding["r{}r".format(i)]
            edge['type'] = 'reverse'
        elif "r{}v".format(i) in grounding:
            edge['kbID'] = grounding["r{}v".format(i)]
            edge['type'] = 'v-structure'

    return grounded


if __name__ == "__main__":
    import doctest

    print(doctest.testmod())