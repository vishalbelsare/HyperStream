# The MIT License (MIT) # Copyright (c) 2014-2017 University of Bristol
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#  DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
#  OR OTHER DEALINGS IN THE SOFTWARE.

from ..utils import Printable, FrozenKeyDict
from node import Node
from factor import Factor
from ..models import WorkflowDefinitionModel, FactorDefinitionModel, NodeDefinitionModel
from ..stream import StreamId, StreamView
from ..errors import StreamNotFoundError
import logging
from collections import defaultdict

import itertools


class Workflow(Printable):
    """
    Workflow. This defines the graph of operations through "nodes" and "factors".
    """
    
    def __init__(self, channels, plates, workflow_id, name, description, owner):
        """
        Initialise the workflow
        :param channels:
        :param plates:
        :param workflow_id:
        :param name:
        :param description:
        :param owner:
        """
        self.channels = channels
        self.plates = plates
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.owner = owner
        self.nodes = {}
        self.factor_collections = defaultdict(list)
        
        logging.info("New workflow created with id {}".format(workflow_id))
    
    def execute(self, time_interval):
        """
        Here we execute the streams in the workflow
        :return:
        """
        # TODO: Currently expects the factors to be declared sequentially
        for factor_collection in self.factor_collections.values()[::-1]:
            for factor in factor_collection:
                logging.debug("Executing factor {}".format(factor))
                factor.execute(time_interval)
            
    def create_node(self, stream_name, channel, plate_ids):
        """
        Create a node in the graph. Note: assumes that the streams already exist
        :param stream_name: The name of the stream
        :param channel: The channel where this stream lives
        :param plate_ids: The plate ids. The stream meta-data will be auto-generated from these
        :return: The streams associated with this node
        """
        streams = []

        if plate_ids:
            for plate_id in plate_ids:
                # Currently allowing multiple plates here
                plate_values = self.plates[plate_id].values

                for pv in plate_values:
                    # Construct stream id
                    stream_id = StreamId(name=stream_name, meta_data=pv)

                    # Now try to locate the stream and add it (raises StreamNotFoundError if not found)
                    # streams.append(self.channels.get_stream(stream_id))
                    streams.append(channel.get_or_create_stream(stream_id=stream_id))
        else:
            streams.append(channel.get_or_create_stream(stream_id=StreamId(name=stream_name)))

        node = Node(stream_name, streams, plate_ids)
        self.nodes[stream_name] = node
        logging.info("Added node with id {}".format(stream_name))
        
        return node
    
    def create_streams(self, channel, stream_name, plate_ids, tool_stream=None):
        """
        Create a node in the graph, using the stream name and plate
        :param channel: the channel containing the stream
        :param stream_name: The name of the stream
        :param plate_ids: The plate ids. The stream meta-data will be auto-generated from these
        :param tool_stream:
        :return: The streams associated with this node
        """
        streams = []
        
        for plate_id in plate_ids:
            # Currently allowing multiple plates here
            plate_values = self.plates[plate_id]
            
            for pv in plate_values:
                # Construct stream id
                stream_id = StreamId(name=stream_name, meta_data=pv)
                
                streams.append(
                    channel.create_stream(
                        stream_id=stream_id,
                        tool_stream=tool_stream
                    )
                )
        
        node = Node(stream_name, streams, plate_ids)
        self.nodes[stream_name] = node
        logging.info("Added node with id {}".format(stream_name))
        
        return node

    def create_factor(self, tool_name, tool_parameters, sources, sink):
        tool_stream = self.channels.tools[StreamId(tool_name)]
        tool_class = tool_stream.items()[-1].value
        tool = tool_class(**tool_parameters)
        factor = Factor(tool=tool, sources=sources, sink=sink)
        self.factor_collections[tool_name].append(factor)
        return factor

    def create_factors(self, tool_name, tool_parameters, output_channel, output_stream_name,
                       plate_ids=None, node_names=None):
        # TODO: TD Version
        factors = []

        if plate_ids:
            for plate_id in plate_ids:
                for pv in self.plates[plate_id]:
                    if not node_names:
                        node_names = []

                    source_ids = [self.nodes[node_name].intersection(pv)
                                  for node_name in node_names if node_name in self.nodes]

                    if source_ids:
                        logging.debug("Found source ids: {}".format(", ".join(source_ids)))
                    else:
                        logging.debug("No source ids found")

                    sources = [self.channels.get_stream(source_id) for source_id in source_ids]
                    sink = output_channel.create_stream(
                        stream_id=StreamId(output_stream_name, pv)
                    )

                    factor = self.create_factor(
                        tool_name=tool_name,
                        tool_parameters=tool_parameters,
                        sources=[StreamView(s) for s in sources],
                        sink=StreamView(sink)
                    )

                    factors.append(factor)
        else:
            factor = self.create_factor(
                tool_name=tool_name,
                tool_parameters=tool_parameters,
                sources=None,
                sink=StreamView(output_channel.create_stream(stream_id=StreamId(output_stream_name)))
            )

            factors.append(factor)

        # self.factor_collections[tool_name] = factors

        # Create output node at the same time
        output_node = Node(
            node_id=output_stream_name,
            streams=[factor.sink for factor in factors],
            plate_ids=plate_ids
        )

        self.nodes[output_stream_name] = output_node

        return factors, output_node

    def create_factors_old(self, tooling_callback, output_channel, output_stream_name, plate_ids, node_names):
        factors = []
        
        for plate_id in plate_ids:
            for pv in self.plates[plate_id]:
                sources_ids = [self.nodes[node_name].intersection(pv)
                               for node_name in node_names if node_name in self.nodes]
                sources = [self.channels.get_stream(sources_id) for sources_id in sources_ids]
                
                sink = output_channel.create_stream(
                    stream_id=StreamId(output_stream_name, pv),
                    tool_stream=tooling_callback(sources)
                )
                
                factor = Factor(
                    tool=sink.tool,
                    sources=sources,
                    sink=sink
                )
                
                factors.append(factor)
        
        self.factor_collections[output_stream_name] = factors
        
        self.nodes[output_stream_name] = Node(
            node_id=output_stream_name,
            streams=[factor.sink for factor in factors],
            plate_ids=plate_ids
        )
        
        return self.factor_collections[output_stream_name]


class WorkflowManager(Printable):
    """
    Workflow manager
    """
    
    def __init__(self, channels, plates):
        """

        :param channels:
        :param plates:
        """
        self.channels = channels
        self.plates = plates
        
        self.workflows = FrozenKeyDict()
        self.uncommitted_workflows = set()
        
        for workflow_definition in WorkflowDefinitionModel.objects():
            try:
                workflow = Workflow(
                    channels=channels,
                    plates=plates,
                    workflow_id=workflow_definition.workflow_id,
                    name=workflow_definition.name,
                    description=workflow_definition.description,
                    owner=workflow_definition.owner
                )
                
                for n in workflow_definition.nodes:
                    # TODO from niall: note, changed create_node to take only two arguments.
                    #   rest: please think about whether we can always guarantee that node_id == n.stream_name
                    workflow.create_node(n.stream_name, channels.get_channel(n.channel_id), n.plate_ids)
                
                # NOTE that we have to replicate the factor over the plate
                # This is fairly simple in the case of
                # 1. a single plate.
                # However we can have:
                # 2. nested plates
                # 3. intersecting plates
                # 4. a combination of 2. and 3.
                for f in workflow_definition.factors:
                    continue
                    source_nodes = [workflow.nodes[s] for s in f.sources]
                    sink_node = workflow.nodes[f.sink]
                    
                    # sort the plate lists by increasing length
                    factor_plates = sorted([plates[plate_id] for plate_id in
                                            list(itertools.chain.from_iterable(s.plate_ids for s in source_nodes))],
                                           key=lambda x: len(x))
                    
                    # TODO: Here we need to get the subgraph of the plate tree so that we can build our for loops later
                    # TODO: One for loop for each level of nesting
                    # TODO: populate input streams
                    tool = channels.get_tool(f.tool.name, f.tool.parameters, input_streams=[])
                    workflow.create_factor(tool, source_nodes, sink_node)
                
                self.add_workflow(workflow, False)
            except StreamNotFoundError as e:
                logging.error(str(e))
    
    def add_workflow(self, workflow, commit=False):
        """

        :param workflow:
        :param commit:
        :return:
        """
        self.workflows[workflow.workflow_id] = workflow
        logging.info("Added workflow {} to workflow manager".format(workflow.workflow_id))
        
        # Optionally also save the workflow to database
        if commit:
            self.commit_workflow(workflow.workflow_id)
        else:
            self.uncommitted_workflows.add(workflow.workflow_id)
    
    def commit_workflow(self, workflow_id):
        """

        :param workflow_id:
        :return:
        """
        # TODO: We should also be committing the Stream definitions if there are new ones
        
        workflow = self.workflows[workflow_id]
        
        workflow_definition = WorkflowDefinitionModel(
            workflow_id=workflow.workflow_id,
            name=workflow.name,
            description=workflow.description,
            nodes=[NodeDefinitionModel(stream_name=n.stream_name, plate_ids=n.plate_ids) for n in workflow.nodes],
            factors=[FactorDefinitionModel(tool=f.tool, sources=[s.stream_id for s in f.sources], sink=f.sink.stream_id)
                     for f in workflow.factors],
            owner=workflow.owner
        )
        
        workflow_definition.save()
        self.uncommitted_workflows.remove(workflow_id)
        logging.info("Committed workflow {} to database".format(workflow_id))
    
    def commit_all(self):
        """
        Commit all workflows to the database
        :return:
        """
        for workflow_id in self.uncommitted_workflows:
            self.commit_workflow(workflow_id)
    
    # def execute_all(self):
    #     """
    #     Execute all workflows
    #     """
    #     for workflow in self.workflows:
    #         self.workflows[workflow].execute()
    
    def create_plate(self, plate, commit=False):
        """
        Create a plate. Make sure all workflows can use it, and optionally commit it to database
        :param plate: The plate
        :param commit: Commit to database
        :return: None
        """
        # TODO: Add the plate, make sure all workflows can use it, and optionally commit it to database
        raise NotImplementedError
