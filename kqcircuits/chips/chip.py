# Copyright (c) 2019-2020 IQM Finland Oy.
#
# All rights reserved. Confidential and proprietary.
#
# Distribution or reproduction of any information contained herein is prohibited without IQM Finland Oy’s prior
# written permission.

import sys
import numpy
from importlib import reload
from autologging import logged, traced

from kqcircuits.defaults import default_layers
from kqcircuits.elements.chip_frame import ChipFrame
from kqcircuits.elements.element import Element
from kqcircuits.elements.launcher import Launcher
from kqcircuits.elements.launcher_dc import LauncherDC
from kqcircuits.pya_resolver import pya
from kqcircuits.test_structures.junction_test_pads import JunctionTestPads
from kqcircuits.test_structures.stripes_test import StripesTest
from kqcircuits.util.merge import merge_layers
from kqcircuits.util.groundgrid import make_grid


reload(sys.modules[Element.__module__])


@traced
@logged
class Chip(Element):
    """Base PCell declaration for chips.

    By default produces in face 0 the chip frame consisting of texts in pixel corners, dicing edge, markers and
    optionally grid. Production of the chip frames can be adjusted by overriding the produce_frames() method.

    Provides helpers to produce launchers and junction tests.
    """
    version = 2

    LIBRARY_NAME = "Chip Library"
    LIBRARY_DESCRIPTION = "Superconducting quantum circuit library for chips."
    LIBRARY_PATH = "chips"

    PARAMETERS_SCHEMA = {
        "box": {
            "type": pya.PCellParameterDeclaration.TypeShape,
            "description": "Border",
            "default": pya.DBox(pya.DPoint(0, 0), pya.DPoint(10000, 10000))
        },
        "with_grid": {
            "type": pya.PCellParameterDeclaration.TypeBoolean,
            "description": "Make ground plane grid",
            "default": False
        },
        "dice_width": {
            "type": pya.PCellParameterDeclaration.TypeDouble,
            "description": "Dicing width [μm]",
            "default": 200
        },
        "name_mask": {
            "type": pya.PCellParameterDeclaration.TypeString,
            "description": "Name of the mask",
            "default": "M99"
        },
        "name_chip": {
            "type": pya.PCellParameterDeclaration.TypeString,
            "description": "Name of the chip",
            "default": "CTest"
        },
        "name_copy": {
            "type": pya.PCellParameterDeclaration.TypeString,
            "description": "Name of the copy"
        },
        "dice_grid_margin": {
            "type": pya.PCellParameterDeclaration.TypeDouble,
            "description": "Margin between dicing edge and ground grid",
            "default": 100,
            "hidden": True
        },
    }

    def display_text_impl(self):
        # Provide a descriptive text for the cell
        return "{}".format(self.name_chip)

    def can_create_from_shape_impl(self):
        return self.shape.is_box()

    def parameters_from_shape_impl(self):
        self.box.p1 = self.shape.p1
        self.box.p2 = self.shape.p2

    @staticmethod
    def get_launcher_assignments(chip_cell):
        """Returns a dictionary of launcher assignments (port_id: launcher_id) for the chip.

        Args:
            chip_cell: Cell object of the chip
        """

        launcher_assignments = {}

        for inst in chip_cell.each_inst():
            port_name = inst.property("port_id")
            if port_name is not None:
                launcher_assignments[port_name] = inst.property("id")

        return launcher_assignments

    def produce_launcher(self, pos, direction, name, port_id, width, launcher_type="RF"):
        """Inserts a launcher in the chip.

        Args:
            pos: position of the launcher
            direction: float rotation in degrees, or one of "E", "W", "S", "N"
            name: name inserted as property "id" in the launcher
            port_id: id inserted as property "port_id" in the launcher
            width: controls the pad width and tapering length of the launcher
            launcher_type: type of the launcher, "RF" or "DC"
        """

        if launcher_type == "RF":
            launcher_cell = self.add_element(Launcher, s=width, l=width)
        elif launcher_type == "DC":
            launcher_cell = self.add_element(LauncherDC, width=width)

        if isinstance(direction, str):
            direction = {"E": 0, "W": 180, "S": -90, "N": 90}[direction]
        transf = pya.DCplxTrans(1, direction, False, pos)
        launcher_inst, launcher_refpoints = self.insert_cell(launcher_cell, transf, name)
        launcher_inst.set_property("port_id", port_id)
        self.add_port(name, launcher_refpoints["port"])

    def produce_launchers_SMA8(self, enabled=["WS", "WN", "ES", "EN", "SW", "SE", "NW", "NE"],
                               launcher_assignments=None):
        """Produces enabled launchers for SMA8 sample holder default locations.

        Args:
            enabled: List of enabled standard launchers from set ("WS", "WN", "ES", "EN", "SW", "SE", "NW", "NE")
            launcher_assignments: dictionary of (port_id: name) that assigns a role to some of the launchers

        Effect:
            launchers PCells added to the class parent cell.

        Returns:
            launchers as a dictionary :code:`{name: (point, heading, distance from chip edge)}`
        """
        # dictionary of point, heading, distance from chip edge
        launchers = {
            "WS": (pya.DPoint(800, 2800), "W", 300),
            "ES": (pya.DPoint(9200, 2800), "E", 300),
            "WN": (pya.DPoint(800, 7200), "W", 300),
            "EN": (pya.DPoint(9200, 7200), "E", 300),
            "SW": (pya.DPoint(2800, 800), "S", 300),
            "NW": (pya.DPoint(2800, 9200), "N", 300),
            "SE": (pya.DPoint(7200, 800), "S", 300),
            "NE": (pya.DPoint(7200, 9200), "N", 300)
        }
        launcher_map = self._create_launcher_map({name: name for name in launchers.keys()}, launcher_assignments)

        for port_id in enabled:
            launcher = launchers[port_id]
            self.produce_launcher(launcher[0], launcher[1], launcher_map[port_id], port_id, launcher[2])
        return launchers

    def produce_launchers_ARD24(self, launcher_assignments=None):
        """Produces launchers for ARD24 sample holder default locations.

         Args:
            launcher_assignments: dictionary of (port_id: name) that assigns a role to some of the launchers

        Effect:
            launchers PCells added to the class parent cell.

        Returns:
            launchers as a dictionary :code:`{name: (point, heading, distance from chip edge)}`
        """
        launchers = self._produce_24_launchers("RF", 240, [i for i in range(1, 25)], launcher_assignments, 1200)
        return launchers

    def produce_launchers_DC(self, enabled=[i for i in range(1, 25)], launcher_assignments=None):
        """Produces launchers for DC sample holder default locations.

        Args:
            enabled: List of enabled standard launchers from integers between 1 and 24
            launcher_assignments: dictionary of (port_id: name) that assigns a role to some of the launchers

        Returns:
            launchers as a dictionary :code:`{name: (point, heading, distance from chip edge)}`
        """
        launchers = self._produce_24_launchers("DC", 500, enabled, launcher_assignments, 850)
        return launchers

    def produce_junction_tests(self, squid_name="QCD1"):
        """Produces junction test pads in the chip.

        Args:
            squid_name: A string defining the type of SQUIDs used in the test pads.
                        QCD1 | QCD2 | QCD3 | SIM1

        """
        junction_tests_w = self.add_element(JunctionTestPads,
            margin=50,
            area_height=1300,
            area_width=2500,
            junctions_horizontal=True,
            squid_name=squid_name,
            display_name="JunctionTestsHorizontal",
        )
        junction_tests_h = self.add_element(JunctionTestPads,
            margin=50,
            area_height=2500,
            area_width=1300,
            junctions_horizontal=True,
            squid_name=squid_name,
            display_name="JunctionTestsVertical",
        )
        self.insert_cell(junction_tests_h, pya.DTrans(0, False, .35e3, (10e3 - 2.5e3) / 2), "testarray_w")
        self.insert_cell(junction_tests_w, pya.DTrans(0, False, (10e3 - 2.5e3) / 2, .35e3), "testarray_s")
        self.insert_cell(junction_tests_h, pya.DTrans(0, False, 9.65e3 - 1.3e3, (10e3 - 2.5e3) / 2), "testarray_e")
        self.insert_cell(junction_tests_w, pya.DTrans(0, False, (10e3 - 2.5e3) / 2, 9.65e3 - 1.3e3), "testarray_n")

    def produce_opt_lit_tests(self):
        """Produces optical lithography test stripes at chip corners."""

        num_stripes = 20
        length = 100
        min_width = 1
        max_width = 15
        step = 3
        first_stripes_width = 2*num_stripes*min_width

        combined_cell = self.layout.create_cell("Stripes")
        for i, width in enumerate(numpy.arange(max_width + 0.1*step, min_width, -step)):
            stripes_cell = self.add_element(StripesTest, num_stripes=num_stripes, stripe_width=width,
                                                                 stripe_length=length)
            # horizontal
            combined_cell.insert(pya.DCellInstArray(stripes_cell.cell_index(),
                                                    pya.DCplxTrans(1, 0, False, -880, 2*i*length +
                                                                   first_stripes_width-200)))
            # vertical
            combined_cell.insert(pya.DCellInstArray(stripes_cell.cell_index(),
                                                    pya.DCplxTrans(1, 90, False,
                                                                   2*i*length + length + first_stripes_width-200,
                                                                   -880)))
            # diagonal
            diag_offset = 2*num_stripes*width/numpy.sqrt(8)
            combined_cell.insert(pya.DCellInstArray(stripes_cell.cell_index(),
                                                    pya.DCplxTrans(1, -45, False, 250 + i*length - diag_offset,
                                                                   250 + i*length + diag_offset)))

        self.insert_cell(combined_cell, pya.DCplxTrans(1, 0, False, 1500, 1500))
        self.insert_cell(combined_cell, pya.DCplxTrans(1, 90, False, 8500, 1500))
        self.insert_cell(combined_cell, pya.DCplxTrans(1, 180, False, 8500, 8500))
        self.insert_cell(combined_cell, pya.DCplxTrans(1, 270, False, 1500, 8500))

    def produce_ground_grid(self):
        """Produces ground grid on the face of the element.

        This method is called in produce_impl(). Override this method to produce a different set of chip frames.
        """
        self.produce_ground_on_face_grid(self.box, 0)

    def produce_ground_on_face_grid(self, box, face_id):
        """Produces ground grid in the given face of the chip.

        Args:
            box: pya.DBox within which the grid is created
            face_id (str): ID of the face where the grid is created

        """
        grid_area = box * (1 / self.layout.dbu)
        protection = pya.Region(self.cell.begin_shapes_rec(self.get_layer("ground grid avoidance", face_id))).merged()
        grid_mag_factor = 1
        region_ground_grid = make_grid(grid_area, protection,
                                       grid_step=10 * (1 / self.layout.dbu) * grid_mag_factor,
                                       grid_size=5 * (1 / self.layout.dbu) * grid_mag_factor)
        self.cell.shapes(self.get_layer("ground grid", face_id)).insert(region_ground_grid)

    def produce_frame(self, frame_parameters, trans=pya.DTrans()):
        """"Produces a chip frame and markers for the given face.

        Args:
            frame_parameters: PCell parameters for the chip frame
            trans: DTrans for the chip frame, default=pya.DTrans()
        """
        self.insert_cell(ChipFrame, trans, **frame_parameters)

    def merge_layout_layers_on_face(self, face):
        """
          Shapes in "base metal gap" layer must be created by combining the "base metal gap wo grid" and
          "ground grid" layers even if no grid is generated

          This method is called in produce_impl(). Override this method to produce a different set of chip frames.
          """

        merge_layers(self.layout, [self.cell], face["base metal gap wo grid"], face["ground grid"],
                     face["base metal gap"])

    def merge_layout_layers(self):
        """
          Shapes in "base metal gap" layer must be created by combining the "base metal gap wo grid" and
          "ground grid" layers even if no grid is generated

          """
        self.merge_layout_layers_on_face(self.face(0))

    def produce_structures(self):
        """Produces chip frame and possibly other structures before the ground grid.

        This method is called in produce_impl(). Override this method to produce a different set of chip frames.
        """
        b_frame_parameters = {
            **self.pcell_params_by_name(whitelist=ChipFrame.PARAMETERS_SCHEMA),
            "use_face_prefix": False
        }
        self.produce_frame(b_frame_parameters)

    def produce_impl(self):
        self.produce_structures()
        if self.with_grid:
            self.produce_ground_grid()
        self.merge_layout_layers()
        self._produce_instance_name_labels()
        super().produce_impl()

    def _produce_instance_name_labels(self):

        for inst in self.cell.each_inst():
            inst_id = inst.property("id")
            if inst_id:
                cell = self.layout.create_cell("TEXT", "Basic", {
                    "layer": default_layers["instance names"],
                    "text": inst_id,
                    "mag": 400.0
                })
                label_trans = inst.dcplx_trans
                # prevent the label from being upside-down or mirrored
                if 90 < label_trans.angle < 270:
                    label_trans.angle += 180
                label_trans.mirror = False
                # optionally apply relative transformation to the label
                rel_label_trans_str = inst.property("label_trans")
                if rel_label_trans_str is not None:
                    rel_label_trans = pya.DCplxTrans.from_s(rel_label_trans_str)
                    label_trans = label_trans * rel_label_trans
                self.insert_cell(cell, label_trans)

    @staticmethod
    def _create_launcher_map(default_launcher_map, launcher_assignments):
        """Returns launcher map, which is a dictionary of (port_id: launcher_id).

        Args:
            default_launcher_map: default value for the launcher map
            launcher_assignments: used to replace certain elements in default_launcher_map

        """
        launcher_map = default_launcher_map
        if launcher_assignments is not None:
            for key, value in launcher_assignments.items():
                launcher_map[key] = value
        return launcher_map

    def _produce_24_launchers(self, launcher_type, launcher_width, enabled, launcher_assignments, pad_pitch):
        """Produces 24 launchers at default locations.

        Args:
            launcher_type: type of the launchers, "RF" or "DC"
            launcher_width: width of the launchers
            enabled: List of enabled standard launchers from integers between 1 and 24
            launcher_assignments: dictionary of (port_id: name) that assigns a role to some of the launchers
            pad_pitch: distance between pad centers

        Returns:
            launchers as a dictionary :code:`{name: (point, heading, distance from chip edge)}`
        """
        launcher_map = self._create_launcher_map({i: str(i) for i in range(1, 25)}, launcher_assignments)

        launchers = {}  # dictionary of point, heading, distance from chip edge
        launchers_specs = []
        for direction, rot, trans in (
                ("N", pya.DTrans.R270, pya.DTrans(3, 0, 0, 10e3)), ("E", pya.DTrans.R180, pya.DTrans(2, 0, 10e3, 10e3)),
                ("S", pya.DTrans.R90, pya.DTrans(1, 0, 10e3, 0)), ("W", pya.DTrans.R0, pya.DTrans(0, 0, 0, 0))):
            for i in range(6):
                loc = pya.DPoint(680, pad_pitch*i + (10000 - pad_pitch*5)/2)
                launchers_specs.append((trans*loc, direction, launcher_width))

        for i, spec in enumerate(launchers_specs):
            port_id = i + 1
            if port_id in enabled:
                name = launcher_map[port_id]
                launchers[name] = spec
                self.produce_launcher(spec[0], spec[1], name, port_id, launcher_width, launcher_type=launcher_type)

        return launchers