import logging
import click
import numpy as np
import yaml
import sys
import tqdm
import json

from datasets import webquestions_io
from construction import staged_generation, stages
from wikidata import wdaccess

np.random.seed(1)


@click.command()
@click.argument('config_file_path', default="default_config.yaml")
def generate(config_file_path):

    with open(config_file_path, 'r') as config_file:
        config = yaml.load(config_file.read())
    print(config)
    config_global = config.get('global', {})
    if "webquestions" not in config:
        print("Dataset location not in the config file!")
        sys.exit()

    if "generation" not in config:
        print("Generation parameters not in the config file!")
        sys.exit()

    np.random.seed(config_global.get('random.seed', 1))

    logger = logging.getLogger(__name__)
    logger.setLevel(config['logger']['level'])
    ch = logging.StreamHandler()
    ch.setLevel(config['logger']['level'])
    logger.addHandler(ch)
    # logging.basicConfig(level=config['logger']['level'])

    webquestions = webquestions_io.WebQuestions(config['webquestions'])

    logger.debug('Extracting entities.')
    webquestions_entities = webquestions.extract_question_entities()
    webquestions_tokens = webquestions.get_dataset_tokens()

    logger.debug('Generating choice graphs')
    choice_graphs_sets = []
    for i in tqdm.trange(100):
        ungrounded_graph = {'tokens': webquestions_tokens[i],
                            'edgeSet': [],
                            'entities': webquestions_entities[i][:config['generation'].get("max.num.entities", 1)]}
        choice_graphs = staged_generation.generate_without_gold(ungrounded_graph)
        choice_graphs_sets.append(choice_graphs)

    logger.debug('Generation is finished')
    with open(config['generation']["save.choice.to"], 'w') as out:
        json.dump(choice_graphs_sets, out, sort_keys=True, indent=4)

    logger.debug("Query cache: {}".format(len(wdaccess.query_cache)))
    logger.debug("Number of answers covered: {}".format(
        sum(1 for graphs in choice_graphs_sets if len(graphs) > 0) / len(webquestions_tokens) ))
    logger.debug("Average number of choices per question: {}".format(
        np.mean([len(graphs) for graphs in choice_graphs_sets])))


if __name__ == "__main__":
    generate()