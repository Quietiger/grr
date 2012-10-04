#!/usr/bin/env python

# Copyright 2011 Google Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A viewer for the timeline objects."""

import functools
import urllib

from grr.gui import renderers
from grr.gui.plugins import fileview
from grr.lib import aff4
from grr.lib import utils


class TimelineViewRenderer(renderers.RDFValueRenderer):
  """Render a container View.

  Post Parameters:
    - aff4_path: The path to the currently drawn object.
  """
  ClassName = "TimelineView"

  layout_template = renderers.Template("""
<a href='#{{this.hash|escape}}'
   onclick='grr.loadFromHash("{{this.hash|escape}}");'
   class="grr-button grr-button-red">
  View details.
</a>
""")

  def Layout(self, request, response):
    client_id = request.REQ.get("client_id")

    container = request.REQ.get("aff4_path", "")
    if container:
      self.container = aff4.RDFURN(container)
      self.hash_dict = dict(
          container=self.container, main="TimelineMain", c=client_id,
          reason=request.token.reason)
      self.hash = urllib.urlencode(self.hash_dict)

      return super(TimelineViewRenderer, self).Layout(request, response)


class TimelineMain(renderers.TemplateRenderer):
  """This is the main view to the timeline.

  Internal State (from hash value):
    - container: The container name for the timeline.
    - query: The query to filter.
  """

  layout_template = renderers.Template("""
<div id='toolbar_{{id|escape}}' class=toolbar></div>
<div id='{{unique|escape}}'></div>
<script>
  var state = {
    container: grr.hash.container,
    query: grr.hash.query || "",
  };

  grr.layout("TimelineToolbar", "toolbar_{{id|escapejs}}", state);
  grr.layout("TimelineViewerSplitter", "{{unique|escapejs}}", state);
  grr.subscribe("GeometryChange", function () {
    grr.fixHeight($("#{{unique|escapejs}}"));
  }, "{{unique|escapejs}}");
</script>
""")


class TimelineViewerSplitter(renderers.Splitter2Way):
  """This is the main view to browse files.

  Internal State:
    - container: The container name for the timeline.
  """

  top_renderer = "EventTable"
  bottom_renderer = "EventViewTabs"

  def Layout(self, request, response):
    self.state["container"] = request.REQ.get("container")
    return super(TimelineViewerSplitter, self).Layout(request, response)


class TimelineToolbar(renderers.TemplateRenderer):
  """A navigation enhancing toolbar.

  Generated Javascript Events:
    - query_changed(query): When the user submits a new query.
    - hash_state(query): When the user submits a new query.

  Post Parameters:
    - container: The container name for the timeline.
    - query: The query to filter.
  """

  layout_template = renderers.Template("""
<form id="csv_{{unique|escape}}" action="/render/Download/EventTable"
   METHOD=post target='_blank'>
<input type="hidden" name='container' value='{{this.container|escape}}' />
<input type="hidden" id="csv_query" />
<input type=hidden name='reason' value='{{this.token.reason|escape}}'>
<button id='export' title="Export to CSV">
<img src="/static/images/stock-save.png">
</button>
{{this.container|escape}}
</form>

<form id="form_{{unique|escape}}" name="query_form">
Filter Expression
<input type="text" id="query" name="query"
  value="{{this.query|escape}}" size=180></input>
</form>
<script>

$('#export').button().click(function () {
  $("input#csv_query").val($("input#query").val());
  $("#csv_{{unique|escape}}").submit();
});

$("#form_{{unique|escapejs}}").submit(function () {
  var query = $("input#query").val();
  grr.publish('query_changed', query);
  grr.publish('hash_state', 'query', query);

  return false;
});
</script>
""")

  def Layout(self, request, response):
    """Render the toolbar."""
    self.container = request.REQ.get("container")
    self.query = request.REQ.get("query", "")
    self.token = request.token

    return super(TimelineToolbar, self).Layout(request, response)


class EventMessageRenderer(renderers.RDFValueRenderer):
  """Render a special message to describe the event based on its type."""

  # If the type is unknown we just say what it is.
  default_template = renderers.Template("""
Event of type {{this.type|escape}}
""")

  event_template_dispatcher = {
      "file.mtime": renderers.Template(
          "<div><pre class='inline'>M--</pre> File modified.</div>"),

      "file.atime": renderers.Template(
          "<div><pre class='inline'>-A-</pre> File access.</div>"),

      "file.ctime": renderers.Template(
          "<div><pre class='inline'>--C</pre> File metadata changed.</div>"),
      }

  def Layout(self, request, response):
    self.type = self.proxy.type
    self.layout_template = self.event_template_dispatcher.get(
        self.type, self.default_template)

    return super(EventMessageRenderer, self).Layout(request, response)


class EventTable(renderers.TableRenderer):
  """Render all the events in a table.

  Listening Javascript Events:
    - query_changed(query): Re-renders the table with the new query.

  Generated Javascript Events:
    - event_select(event_id): When the user selects an event from the
      table. event_id is the sequential number of the event from the start of
      the time series.

  Internal State/Post Parameters:
    - container: The container name for the timeline.
    - query: The query to filter.
  """

  layout_template = renderers.TableRenderer.layout_template + """
<script>
  grr.subscribe("query_changed", function (query) {
    grr.layout("{{renderer|escapejs}}", "{{id|escapejs}}", {
      container: "{{this.state.container|escapejs}}",
      query: query,
    });
  }, "{{unique|escapejs}}");

  grr.subscribe("select_table_{{ id|escapejs }}", function(node) {
    var event_id = node.find("td").first().text();

    grr.publish("event_select", event_id);
  }, '{{ unique|escapejs }}');

</script>
"""
  content_cache = None

  def __init__(self):
    if EventTable.content_cache is None:
      EventTable.content_cache = utils.TimeBasedCache()
    super(EventTable, self).__init__()
    self.AddColumn(renderers.AttributeColumn("event.id", width=0))
    self.AddColumn(renderers.AttributeColumn("timestamp", width=10))
    self.AddColumn(renderers.AttributeColumn("subject"))
    self.AddColumn(renderers.RDFValueColumn(
        "Message", renderer=EventMessageRenderer))

  def Layout(self, request, response):
    """Render the content of the tab or the container tabset."""
    self.state["container"] = request.REQ.get("container")
    self.state["query"] = request.REQ.get("query", "")
    return super(EventTable, self).Layout(request, response)

  def BuildTable(self, start_row, end_row, request):
    """Populate the table."""
    query = request.REQ.get("query", "")
    container = request.REQ.get("container")

    key = utils.SmartUnicode(container)
    key += ":" + query + ":%d"
    try:
      events = self.content_cache.Get(key % start_row)
      self.content_cache.ExpireObject(key % start_row)
      act_row = start_row
    except KeyError:
      fd = aff4.FACTORY.Open(container, token=request.token)
      events = fd.Query(query)
      act_row = 0

    for child in events:
      if act_row < start_row:
        act_row += 1
        continue

      # Add the event to the special message renderer.
      self.AddCell(act_row, "Message", child.event)

      # Add the fd to all the columns
      for column in self.columns:
        # This sets AttributeColumns directly from their fd.
        if isinstance(column, renderers.AttributeColumn):
          column.AddRowFromFd(act_row, child)

      act_row += 1
      if act_row >= end_row:
        # Tell the table there are more rows.
        self.size = act_row + 1
        self.content_cache.Put(key % act_row, events)
        return


class EventViewTabs(renderers.TabLayout):
  """Show tabs to allow inspection of the event.

  Listening Javascript Events:
    - event_select(event_id): Indicates the user has selected this event in the
      table, we re-render ourselves with the new event_id.

  Post Parameters:
    - container: The container name for the timeline.
    - event: The event id within the timeseries container to render.
  """

  event_queue = "event_select"
  names = ["Event", "Subject"]
  delegated_renderers = ["EventView", "EventSubjectView"]

  # Listen to the event change events and switch to the first tab.
  layout_template = renderers.TabLayout.layout_template + """
<script>
grr.subscribe("{{ this.event_queue|escapejs }}", function(event) {
  grr.publish("hash_state", "event", event);
  grr.layout("{{renderer|escapejs}}", "{{id|escapejs}}", {
    event: event,
    container: "{{this.state.container|escapejs}}",
  });
}, 'tab_contents_{{unique|escapejs}}');
</script>
"""

  def Layout(self, request, response):
    """Check if the file is a readable and disable the tabs."""
    self.state["container"] = request.REQ.get("container")
    self.state["event"] = request.REQ.get("event")
    return super(EventViewTabs, self).Layout(request, response)


class EventSubjectView(fileview.AFF4Stats):
  """View the subject of the event.

  Post Parameters:
    - container: The container name for the timeline.
    - event: The event id.
  """

  def GetEvent(self, request):
    event_id = request.REQ.get("event")
    if event_id is not None and event_id != "null":
      event_id = int(event_id)
      container = request.REQ.get("container")
      fd = aff4.FACTORY.Open(container, token=request.token)

      child = None
      for child in fd:
        # Found the right event.
        if child.id == event_id:
          return child

  def Layout(self, request, response):
    """Find the event and show stats about it."""
    event = self.GetEvent(request)
    if event:
      subject = aff4.FACTORY.Open(event.subject, token=request.token,
                                  age=aff4.ALL_TIMES)
      self.classes = self.RenderAFF4Attributes(subject, request)
      self.path = subject.urn

      return super(EventSubjectView, self).Layout(request, response)


class EventView(EventSubjectView):
  """View the event details."""

  error_message = renderers.Template(
      "Please select an event in the table above.")

  def Layout(self, request, response):
    """Retrieve the event aff4 object."""
    event = self.GetEvent(request)
    if event:
      event_class = aff4.AFF4Object.classes["AFF4Event"]
      self.classes = self.RenderAFF4Attributes(event_class(event), request)
      self.path = "Event %s at %s" % (event.id,
                                      aff4.RDFDatetime(event.timestamp))

      return renderers.TemplateRenderer.Layout(self, request, response)

    # Just return a generic error message.
    return renderers.TemplateRenderer.Layout(self, request, response,
                                             self.error_message)


class RDFEventRenderer(renderers.RDFProtoRenderer):
  """A renderer for Event Protobufs."""
  ClassName = "RDFEvent"
  name = "Event"

  translator = dict(
      # The stat field is rendered using the StatEntryRenderer.
      stat=functools.partial(renderers.RDFProtoRenderer.RDFProtoRenderer,
                             proto_renderer_name="StatEntryRenderer"))