"""
Custom Dashboards.

| Copyright 2017-2024, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import enum
import numpy as np
import random
from textwrap import dedent

import fiftyone as fo
import fiftyone.operators as foo
import fiftyone.operators.types as types
import fiftyone.types as fot
import fiftyone.core.fields as fof
from fiftyone import ViewField as F


class PlotlyPlotType(enum.Enum):
    bar = "bar"
    scatter = "scatter"
    line = "line"
    pie = "pie"


class PlotType(enum.Enum):
    categorical_histogram = "categorical_histogram"
    numeric_histogram = "numeric_histogram"
    line = "line"
    scatter = "scatter"
    pie = "pie"


NUMERIC_TYPES = (
    fof.IntField,
    fof.FloatField,
)

CATEGORICAL_TYPES = (
    fof.StringField,
    fof.BooleanField,
    fof.IntField,
    fof.FloatField,
)


def get_plotly_plot_type(plot_type):
    if plot_type == PlotType.categorical_histogram:
        return PlotlyPlotType.bar
    elif plot_type == PlotType.numeric_histogram:
        return PlotlyPlotType.bar
    elif plot_type == PlotType.line:
        return PlotlyPlotType.line
    elif plot_type == PlotType.scatter:
        return PlotlyPlotType.scatter
    elif plot_type == PlotType.pie:
        return PlotlyPlotType.pie


def get_plotly_config_and_layout(plot_config):
    config = {}
    layout = {}
    if plot_config.get("plot_title"):
        layout["title"] = plot_config.get("plot_title")
    if plot_config.get("color"):
        color = plot_config.get("color")
        layout["marker"] = {"color": color.get("hex")}
    if plot_config.get("xaxis"):
        layout["xaxis"] = plot_config.get("xaxis")
    if plot_config.get("yaxis"):
        layout["yaxis"] = plot_config.get("yaxis")
    if plot_config.get("plot_type") == "numeric_histogram":
        layout["bargap"] = 0
        layout["bargroupgap"] = 0
    return {"config": config, "layout": layout}


requires_x = [PlotType.scatter, PlotType.line, PlotType.numeric_histogram]
requires_y = [PlotType.scatter, PlotType.line]


def get_root(dataset, path):
    root = None
    schema = dataset.get_field_schema(flat=True)
    for _path, field in schema.items():
        if path.startswith(_path + ".") and isinstance(field.fo.ListField):
            root = _path

    return root


def get_fields_with_type(dataset, field_types, root=None):
    schema = dataset.get_field_schema(flat=True)
    paths = []
    for path, field in schema.items():
        if root is not None and not path.startswith(root + "."):
            continue

        if isinstance(field, field_types) or (
            isinstance(field, fo.ListField)
            and isinstance(field.field, field_types)
        ):
            paths.append(path)

    return paths


#
# Types
#


class PlotDefinition(object):
    def __init__(self, plot_type, layout={}, config={}, sources={}, code=None):
        self.plot_type = plot_type
        self.layout = layout
        self.config = config
        self.x_source = sources.get("x", None)
        self.y_source = sources.get("y", None)
        self.z_source = sources.get("z", None)
        self.code = code

    @staticmethod
    def requires_source(cls, plot_type, dim):
        if dim == "x":
            return plot_type in requires_x
        if dim == "y":
            return plot_type in requires_y


class DashboardPlotProperty(types.Property):
    def __init__(self, item, on_click_plot=None, on_plot_select=None):
        name = item.name
        label = item.label
        plot_config = item.config
        plot_layout = item.layout
        x_field = item.x_field
        y_field = item.y_field
        type = types.Object()
        view = types.PlotlyView(
            config=plot_config,
            layout=plot_layout,
            on_click=on_click_plot,
            on_selected=on_plot_select,
            x_data_source=x_field,
            y_data_source=y_field,
        )
        super().__init__(type, view=view)
        self.name = name
        self.label = label

    @staticmethod
    def from_item(item, on_click_plot, on_plot_select):
        return DashboardPlotProperty(
            item, on_click_plot=on_click_plot, on_plot_select=on_plot_select
        )


class DashboardPlotItem(object):
    def __init__(
        self,
        name,
        type,
        config,
        layout,
        raw_params=None,
        use_code=False,
        code=None,
        update_on_change=None,
        x_field=None,
        y_field=None,
        field=None,
        bins=10,
    ):
        self.name = name
        self.type = PlotType(type)
        self.raw_params = raw_params
        self.config = config
        self.layout = layout
        self.use_code = use_code
        self.code = code
        self.update_on_change = update_on_change
        self.x_field = x_field
        self.y_field = y_field
        self.field = field
        self.bins = bins

    @staticmethod
    def from_dict(data):
        return DashboardPlotItem(
            data.get("name"),
            data.get("type"),
            data.get("config"),
            data.get("layout"),
            data.get("raw_params", None),
            data.get("use_code", False),
            data.get("code"),
            data.get("update_on_change"),
            data.get("x_field", None),
            data.get("y_field", None),
            data.get("field", None),
            data.get("bins", 10),
        )

    @property
    def label(self):
        return self.config.get("title", self.name)

    def to_configure_plot_params(self):
        return {**self.raw_params, "name": self.name}

    def to_dict(self):
        return {
            "name": self.name,
            "type": self.type.value,
            "config": self.config,
            "layout": self.layout,
            "raw_params": self.raw_params,
            "use_code": self.use_code,
            "code": self.code,
            "update_on_change": self.update_on_change,
            "x_field": self.x_field,
            "y_field": self.y_field,
            "field": self.field,
            "bins": self.bins,
        }


class DashboardState(object):
    def __init__(self, ctx):
        self.ctx = ctx
        self.panel = ctx.panel
        self._items = {}
        self._data = {}
        items = ctx.panel.get_state("items_config")
        if items:
            for key, item in items.items():
                self._items[key] = DashboardPlotItem.from_dict(item)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.apply_state()
        if exc_type is not None:
            print(f"An exception occurred: {exc_type}, {exc_value}")
        return True

    @property
    def is_empty(self):
        return len(self._items) == 0

    @property
    def view(self):
        return self.ctx.view

    @property
    def items(self):
        return self._items.values()

    @property
    def item_count(self):
        return len(self._items)

    def items_as_dict(self):
        return {k: v.to_dict() for k, v in self._items.items()}

    def apply_state(self):
        items_dict = self.items_as_dict()
        self.panel.set_state("items_config", items_dict)

    def apply_data(self):
        data_paths_dict = {f"items.{k}": v for k, v in self._data.items()}
        self.panel.batch_set_data(data_paths_dict)

    def get_item(self, item_id):
        return self._items.get(item_id, None)

    def remove_item(self, item_id):
        self._items.pop(item_id)
        # TODO: properly handle clearing of state/data

    def clear_items(self):
        self._items = {}

    def get_next_item_id(self):
        return f"plot_{random.randint(0, 1000)}"

    def add_plot(self, item):
        self._items[item.name] = item
        data = self.load_plot_data_for_item(item)
        self._data[item.name] = data
        self.apply_data()

    def edit_plot(self, item):
        self._items[item.name] = item
        data = self.load_plot_data_for_item(item)
        self._data[item.name] = data
        self.apply_data()

    def load_plot_data(self, plot_id):
        item = self.get_item(plot_id)
        if item is None:
            return {}
        return self.load_plot_data_for_item(item)

    def load_plot_data_for_item(self, item):
        if item.use_code:
            return self.load_data_from_code(item.code, item.type)
        if item.type == PlotType.categorical_histogram:
            return self.load_categorical_histogram_data(item)
        elif item.type == PlotType.numeric_histogram:
            return self.load_numeric_histogram_data(item)
        elif item.type == PlotType.scatter:
            return self.load_scatter_data(item)
        elif item.type == PlotType.line:
            return self.load_line_data(item)
        elif item.type == PlotType.pie:
            return self.load_pie_data(item)

    def load_all_plot_data(self):
        for item in self.items:
            data = self.load_plot_data(item.name)
            self._data[item.name] = data
        self.apply_data()

    def load_categorical_histogram_data(self, item):
        field = item.field
        if not field:
            return {}
        counts = self.view.count_values(field)

        histogram_data = {
            "x": list(counts.keys()),
            "y": list(counts.values()),
            "type": "bar",
        }

        return histogram_data

    def load_numeric_histogram_data(self, item):
        x = item.x_field
        bins = item.bins

        if not x:
            return {}

        counts, edges, other = self.view.histogram_values(
            x,
            bins=bins,
        )

        counts = np.asarray(counts)
        edges = np.asarray(edges)

        left_edges = edges[:-1]
        widths = edges[1:] - edges[:-1]

        histogram_data = {
            "x": left_edges.tolist(),
            "y": counts.tolist(),
            "type": "bar",
            "width": widths.tolist(),
        }

        return histogram_data

    def load_scatter_data(self, item):
        x = self.view.values(F(item.x_field))
        y = self.view.values(F(item.y_field))
        ids = self.view.values("id")

        if not x or not y:
            return {}

        scatter_data = {
            "x": x,
            "y": y,
            "ids": ids,
            "type": "scatter",
            "mode": "markers",
        }

        return scatter_data

    def load_line_data(self, item):
        if item.x_field is None or item.y_field is None:
            return {}

        x = self.view.values(F(item.x_field))
        y = self.view.values(F(item.y_field))

        line_data = {"x": x, "y": y, "type": "line"}

        return line_data

    def load_pie_data(self, item):
        field = item.field

        if not field:
            return {}

        counts = self.view.count_values(field)
        values = list(counts.values())
        keys = list(counts.keys())
        sum = np.sum(values)
        factor = 100.0 / sum
        factored_values = [v * factor for v in values]

        pie_data = {
            "values": factored_values,
            "labels": keys,
            "type": "pie",
            "name": item.config.get("title", "Pie Chart"),
        }

        return pie_data

    def load_data_from_code(self, code, plot_type):
        if not code:
            return {}
        local_vars = {}
        try:
            exec(code, {"ctx": self.ctx}, local_vars)
            data = local_vars.get("data", {})
            data["type"] = get_plotly_plot_type(plot_type).value
            return data
        except Exception as e:
            print(f"Error loading data: {e}")
            return {}

    def can_load_data(self, item):
        if item.code:
            return True
        if item.type == PlotType.categorical_histogram:
            return item.field is not None
        elif item.type == PlotType.numeric_histogram:
            return item.x_field is not None
        elif item.type == PlotType.scatter:
            return item.x_field is not None and item.y_field is not None
        elif item.type == PlotType.line:
            return item.x_field is not None and item.y_field is not None
        elif item.type == PlotType.pie:
            return item.field is not None


def can_edit(ctx: foo.executor.ExecutionContext):
    is_teams = hasattr(ctx, "user")
    if is_teams:
        return ctx.user and ctx.user.dataset_permission == "can_edit"
    return True  # for oss


class CustomDashboard(foo.Panel):
    @property
    def config(self):
        return foo.PanelOperatorConfig(
            name="custom_dashboard",
            label="Custom Dashboard",
            description="A custom dashboard",
        )

    #
    # Events
    #

    def on_load(self, ctx):
        dashboard_state = DashboardState(ctx)
        dashboard_state.load_all_plot_data()

    def on_change_view(self, ctx):
        dashboard_state = DashboardState(ctx)
        for item in dashboard_state.items:
            if item.update_on_change:
                data = dashboard_state.load_plot_data(item.name)
                dashboard_state._data[item.name] = data
        dashboard_state.apply_data()

    def on_add(self, ctx):
        if can_edit(ctx):
            ctx.prompt(
                "@voxel51/custom_dashboard/configure_plot",
                on_success=self.on_configure_plot,
            )

    def handle_plot_change(self, ctx, edit=False):
        result = ctx.params.get("result")
        p = get_plotly_config_and_layout(result)
        plot_layout = p.get("layout", {})
        plot_config = p.get("config", {})
        plot_type = result.get("plot_type")
        code = result.get("code", None)
        update_on_change = result.get("update_on_change", None)
        with DashboardState(ctx) as dashboard_state:
            name = result.get("name", dashboard_state.get_next_item_id())
            item = DashboardPlotItem(
                name=name,
                type=plot_type,
                config=plot_config,
                layout=plot_layout,
                raw_params=result,
                use_code=result.get("use_code", False),
                code=code,
                update_on_change=update_on_change,
                x_field=result.get("x_field", None),
                y_field=result.get("y_field", None),
                field=result.get("field", None),
                bins=result.get("bins", 10),
            )
            if edit:
                dashboard_state.edit_plot(item)
            else:
                dashboard_state.add_plot(item)

    def on_configure_plot(self, ctx):
        self.handle_plot_change(ctx)

    def on_edit_success(self, ctx):
        self.handle_plot_change(ctx, edit=True)

    def on_edit(self, ctx):
        plot_id = ctx.params.get("id")
        dashboard_state = DashboardState(ctx)
        item = dashboard_state.get_item(plot_id)
        if item is None:
            return
        if can_edit(ctx):
            ctx.prompt(
                "@voxel51/custom_dashboard/configure_plot",
                on_success=self.on_edit_success,
                params=item.to_configure_plot_params(),
            )

    def on_remove(self, ctx):
        if can_edit(ctx):
            plot_id = ctx.params.get("id")
            with DashboardState(ctx) as dashboard_state:
                dashboard_state.remove_item(plot_id)

    def on_click_plot(self, ctx):
        plot_id = ctx.params.get("relative_path")
        dashboard = DashboardState(ctx)
        item = dashboard.get_item(plot_id)
        if item.use_code or item.type == PlotType.pie:
            return
        x_field = item.x_field
        y_field = item.y_field
        if (
            item.type == PlotType.categorical_histogram
            or item.type == PlotType.numeric_histogram
        ):
            if item.type == PlotType.categorical_histogram:
                x_field = item.field
                x = ctx.params.get("x")
                view = ctx.dataset.match_values(x_field, x)
                ctx.ops.set_view(view)
                return
            range = ctx.params.get("range")
            if range:
                min, max = range
                filter = {}
                filter[x_field] = {"$gte": min, "$lte": max}
                ctx.trigger(
                    "set_view",
                    dict(
                        view=[
                            {
                                "_cls": "fiftyone.core.stages.Match",
                                "kwargs": [["filter", filter]],
                            }
                        ]
                    ),
                )
        if item.type == PlotType.scatter or item.type == PlotType.line:
            range = ctx.params.get("range")
            if range:
                x = ctx.params.get("x")
                y = ctx.params.get("y")
                filter = {}
                filter[x_field] = x
                filter[y_field] = y
                ctx.trigger(
                    "set_view",
                    dict(
                        view=[
                            {
                                "_cls": "fiftyone.core.stages.Match",
                                "kwargs": [["filter", filter]],
                            }
                        ]
                    ),
                )

    def on_plot_select(self, ctx):
        plot_id = ctx.params.get("relative_path")
        dashboard = DashboardState(ctx)
        item = dashboard.get_item(plot_id)
        if item.use_code or item.type == PlotType.pie:
            return
        if item.type == PlotType.scatter or item.type == PlotType.line:
            data = ctx.params.get("data")
            # data[n] = {idx, id}
            ids = [d.get("id") for d in data]
            if len(ids) == 0:
                # this is being triggered from the ui incorrectly after a valid on selected event
                return
            matched_ids_view = ctx.dataset.select(ids)
            ctx.ops.set_view(matched_ids_view)
        pass

    #
    # Load plot data
    #

    def load_data(self, ctx):
        pass

    #
    # Render Properties
    #

    def render_menu(self, ctx):
        menu = types.Object()
        # menu.btn('btn', label='Button')
        return types.Property(menu)

    def render_dashboard(self, ctx, on_click_plot, on_plot_select):
        dashboard = types.Object()
        dashboard_state = DashboardState(ctx)
        for dashboard_item in dashboard_state.items:
            dashboard.add_property(
                dashboard_item.name,
                DashboardPlotProperty.from_item(
                    dashboard_item, on_click_plot, on_plot_select
                ),
            )
        user_can_edit = can_edit(ctx)
        dashboard_view = types.DashboardView(
            on_add_item=self.on_add,
            on_remove_item=self.on_remove,
            on_edit_item=self.on_edit,
            allow_edit=user_can_edit,
            allow_remove=user_can_edit,
            allow_add=user_can_edit,
            width=100,
            height=100 if dashboard_state.is_empty else None,
        )
        return types.Property(dashboard, view=dashboard_view)

    def render(self, ctx):
        panel = types.Object()
        panel.add_property("menu", self.render_menu(ctx))
        panel.add_property(
            "items",
            self.render_dashboard(
                ctx, self.on_click_plot, self.on_plot_select
            ),
        )
        return types.Property(panel, view=types.GridView(padding=0, gap=0))


#
# Operators
#


class ConfigurePlot(foo.Operator):
    @property
    def config(self):
        return foo.OperatorConfig(
            name="configure_plot",
            label="Configure Plot",
            description="Configure a plot",
            dynamic=True,
            unlisted=True,
        )

    def get_number_field_choices(self, ctx):
        fields = types.Choices(space=6)
        paths = get_fields_with_type(ctx.view, NUMERIC_TYPES)
        for field_path in paths:
            fields.add_choice(field_path, label=field_path)
        return fields

    def get_categorical_field_choices(self, ctx):
        fields = types.Choices(space=6)
        paths = get_fields_with_type(ctx.view, CATEGORICAL_TYPES)
        for field_path in paths:
            fields.add_choice(field_path, label=field_path)
        return fields

    def create_axis_input(self, ctx, inputs, axis):
        axis_obj = types.Object()
        axis_bool_view = types.CheckboxView(space=3)
        axis_obj.str("title", default=None, label=f"Title")
        # axis_obj.bool('showgrid', default=True, label="Show Grid", view=axis_bool_view)
        # axis_obj.bool('zeroline', default=False, label="Show Zero Line", view=axis_bool_view)
        # axis_obj.bool('showline', default=True, label="Show Line", view=axis_bool_view)
        # axis_obj.bool('mirror', default=False, label="Mirror", view=axis_bool_view)
        # axis_obj.bool('autotick', default=True, label="Auto Tick", view=axis_bool_view)
        # axis_obj.bool('showticklabels', default=True, label="Show Tick Labels", view=axis_bool_view)
        # axis_obj.bool('showspikes', default=False, label="Show Spikes", view=axis_bool_view)

        # scale_choices = types.Choices()
        # scale_choices.add_choice("linear", label="Linear")
        # scale_choices.add_choice("log", label="Log")
        # scale_choices.add_choice("date", label="Date")
        # scale_choices.add_choice("category", label="Category")
        # axis_obj.enum('type', values=scale_choices.values(), view=scale_choices, default="linear", label="Scale Type")

        # axis_obj.float('tickangle', default=0, label="Tick Angle")
        # axis_obj.str('tickformat', default=None, label="Tick Format", view=types.View(space=3))

        # Range settings
        # axis_obj.bool('autorange', default=True, label="Auto Range", view=axis_bool_view)
        inputs.define_property(
            f"{axis}axis", axis_obj, label=f"{axis.capitalize()} Axis"
        )

    def get_code_example(self, plot_type):
        if plot_type == "categorical_histogram":
            return dedent(
                """
                import random
                categories = ['A', 'B', 'C', 'D', 'E']
                data = {
                    'x': random.choices(categories, k=100),
                }
            """
            ).strip()
        elif plot_type == "numeric_histogram":
            return dedent(
                """
                import numpy as np
                data = {
                    'x': np.random.normal(size=1000),
                }
            """
            ).strip()
        elif plot_type == "line":
            return dedent(
                """
                import numpy as np
                x = np.arange(0, 10, 0.1)
                y = np.sin(x)
                data = {
                    'x': x.tolist(),
                    'y': y.tolist(),
                }
            """
            ).strip()
        elif plot_type == "scatter":
            return dedent(
                """
                import numpy as np
                x = np.random.rand(100)
                y = np.random.rand(100)
                data = {
                    'x': x.tolist(),
                    'y': y.tolist(),
                    'mode': 'markers'
                }
            """
            ).strip()
        elif plot_type == "pie":
            return dedent(
                """
                data = {
                    'values': [33, 33, 33],
                    'labels': ['A', 'B', 'C'],
                }
            """
            ).strip()

    def resolve_input(self, ctx):
        inputs = types.Object()

        plot_choices = types.Choices(label="Plot Type")
        plot_choices.add_choice(
            "categorical_histogram", label="Categorical Histogram"
        )
        plot_choices.add_choice("numeric_histogram", label="Numeric Histogram")
        plot_choices.add_choice("line", label="Line")
        plot_choices.add_choice("scatter", label="Scatter")
        plot_choices.add_choice("pie", label="Pie")

        plot_type = ctx.params.get("plot_type")

        inputs.enum(
            "plot_type",
            values=plot_choices.values(),
            view=plot_choices,
            required=True,
        )
        use_code = ctx.params.get("use_code")

        if plot_type:
            inputs.str(
                "plot_title",
                label="Plot Title",
                description="Displayed above the plot",
            )
            inputs.bool(
                "use_code",
                default=False,
                label="Custom Python Data Source",
                description="Use python to populate plot data",
            )

            if use_code:
                code_example = self.get_code_example(plot_type)
                inputs.str(
                    "code",
                    label="Code Editor",
                    default=code_example,
                    view=types.CodeView(language="python", space=6),
                )
            else:
                number_fields = self.get_number_field_choices(ctx)
                categorical_fields = self.get_categorical_field_choices(ctx)

                if plot_type == "line" or plot_type == "scatter":
                    inputs.enum(
                        "y_field",
                        values=number_fields.values(),
                        view=number_fields,
                        required=True,
                        label="Y Data Source",
                    )
                    self.create_axis_input(ctx, inputs, "y")
                if plot_type != "pie" and plot_type != "categorical_histogram":
                    inputs.enum(
                        "x_field",
                        values=number_fields.values(),
                        view=number_fields,
                        required=True,
                        label="X Data Source",
                    )
                    self.create_axis_input(ctx, inputs, "x")

                if plot_type == "categorical_histogram" or plot_type == "pie":
                    inputs.enum(
                        "field",
                        values=categorical_fields.values(),
                        view=categorical_fields,
                        required=True,
                        label="Category Field",
                    )

            if plot_type == "numeric_histogram":
                inputs.int(
                    "bins",
                    default=10,
                    label="Number of Bins",
                    view=types.View(space=6),
                )

            inputs.bool(
                "update_on_change", default=True, label="Update On View Change"
            )

            # plot preview
            plotly_layout_and_config = get_plotly_config_and_layout(ctx.params)
            preview_config = plotly_layout_and_config.get("config", {})
            preview_layout = plotly_layout_and_config.get("layout", {})
            item = DashboardPlotItem.from_dict(
                {
                    "name": "plot_preview",
                    "type": plot_type,
                    "config": preview_config,
                    "layout": preview_layout,
                    "use_code": ctx.params.get("use_code", False),
                    "code": ctx.params.get("code", None),
                    "x_field": ctx.params.get("x_field", None),
                    "y_field": ctx.params.get("y_field", None),
                    "field": ctx.params.get("field", None),
                    "bins": ctx.params.get("bins", 10),
                }
            )
            db = DashboardState(ctx)
            if db.can_load_data(item):
                preview_data = db.load_plot_data_for_item(item)
                preview_container = inputs.grid(
                    "grid", height="400px", width="100%"
                )
                preview_height = "600px" if plot_type == "pie" else "300px"
                preview_container.plot(
                    "plot_preview",
                    label="Plot Preview",
                    config=preview_config,
                    layout=preview_layout,
                    data=preview_data,
                    height=preview_height,
                    width="600px",
                )

        is_edit = ctx.params.get("name", None) is not None
        submit_button_label = "Update Plot" if is_edit else "Create Plot"
        prompt = types.PromptView(submit_button_label=submit_button_label)

        return types.Property(inputs, view=prompt)

    def execute(self, ctx):
        plot_config = ctx.params
        plot_config.pop(
            "panel_state"
        )  # todo: remove this and panel_state from params
        plotly_layout_and_config = get_plotly_config_and_layout(plot_config)
        return {**ctx.params, **plotly_layout_and_config}


def register(p):
    p.register(ConfigurePlot)
    p.register(CustomDashboard)
