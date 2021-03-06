# The MIT License (MIT)
# Copyright (c) 2014-2017 University of Bristol
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

from hyperstream.tool import MultiOutputTool
from hyperstream.stream import StreamInstance, StreamMetaInstance, AssetStream
from hyperstream.time_interval import TimeInterval, MIN_DATE

from copy import deepcopy
import logging


class StreamBroadcasterFromStream(MultiOutputTool):
    """
    Version of the stream broadcaster that assumes that the output plate values are contained in the last item of the
    splitting (asset) stream
    """
    def __init__(self, func):
        """
        Stream broadcaster from stream

        :param func: The function to be applied to the value in each document
        """
        super(StreamBroadcasterFromStream, self).__init__(func=func)

    def _execute(self, source, splitting_stream, interval, meta_data_id, output_plate_values):
        if splitting_stream is None:
            raise ValueError("Splitting stream required for this tool")

        if isinstance(splitting_stream, AssetStream):
            time_interval = TimeInterval(MIN_DATE, interval.end)
            splitter = splitting_stream.window(time_interval, force_calculation=True).last()
        else:
            splitter = splitting_stream.window(interval, force_calculation=True).last()

        if not splitter:
            logging.debug("No assets found for source {} and splitter {}"
                          .format(source.stream_id, splitting_stream.stream_id))
            return
        try:
            output_plate_values = sorted(set(splitter.value.values()))
        except TypeError:
            raise

        data = self.func(map(deepcopy, source.window(interval, force_calculation=True)))

        if data is None:
            logging.debug("{} found no data for interval {} for source {} and splitter {}"
                          .format(self.name, interval, source.stream_id, splitting_stream.stream_id))
            return

        if isinstance(data, StreamInstance):
            data = [data]

        for doc in data:
            for vv in output_plate_values:
                yield StreamMetaInstance(doc, (meta_data_id, str(vv)))
