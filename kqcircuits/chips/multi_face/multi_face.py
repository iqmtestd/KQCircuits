# Copyright (c) 2019-2020 IQM Finland Oy.
#
# All rights reserved. Confidential and proprietary.
#
# Distribution or reproduction of any information contained herein is prohibited without IQM Finland Oy’s prior
# written permission.

import sys
from importlib import reload
from autologging import traced, logged
from kqcircuits.pya_resolver import pya
from kqcircuits.chips.chip import Chip
from kqcircuits.elements.chip_frame import ChipFrame
from kqcircuits.elements.flip_chip_connector.flip_chip_connector_dc import FlipChipConnectorDc
from kqcircuits.elements.waveguide_coplanar import WaveguideCoplanar
from kqcircuits.defaults import default_mask_parameters

reload(sys.modules[Chip.__module__])


@traced
@logged
class MultiFace(Chip):
    """Base class for multi-face chips.

    Produces labels in pixel corners, dicing edge, markers and optionally grid for all chip faces. Contains methods for
    producing launchers in face 0, connectors between faces 0 and 1, and default routing waveguides from the
    launchers to the connectors.
    """
    version = 1

    PARAMETERS_SCHEMA = {
        "face1_box": {
            "type": pya.PCellParameterDeclaration.TypeShape,
            "description": "Border of Face 1",
            "default": pya.DBox(pya.DPoint(1500, 1500), pya.DPoint(8500, 8500))
        },
        "with_gnd_bumps": {
            "type": pya.PCellParameterDeclaration.TypeBoolean,
            "description": "Make ground bumps",
            "default": False
        },
        "a_capped": {
            "type": pya.PCellParameterDeclaration.TypeDouble,
            "description": "Capped center conductor width [μm]",
            "docstring": "Width of center conductor in the capped region [μm]",
            "default": 10
        },
        "b_capped": {
            "type": pya.PCellParameterDeclaration.TypeDouble,
            "description": "Width of gap in the capped region  [μm]",
            "default": 10
        },
        "connector_type": {
            "type": pya.PCellParameterDeclaration.TypeString,
            "description": "Connector type for CPW waveguides",
            "default": "Coax",
            "choices": [["Single", "Single"], ["GSG", "GSG"], ["Coax", "Coax"]]
        }

    }

    def produce_impl(self):
        super().produce_impl()

    def produce_structures(self):
        # produce frame for face 0
        bottom_frame_parameters = {
            **self.pcell_params_by_name(whitelist=ChipFrame.PARAMETERS_SCHEMA),
            "face_ids": self.face_ids[0],
            "use_face_prefix": True
        }
        self.produce_frame(bottom_frame_parameters)

        # produce frame for face 1
        t_frame_parameters = {
            "box": self.face1_box,
            "marker_dist": 1000,
            "marker_diagonals": 2,
            "face_ids": self.face_ids[1],
            "use_face_prefix": True,
            "name_chip": self.name_chip,
            "name_mask": self.name_mask,
            "dice_width": default_mask_parameters[self.face_ids[1]]["dice_width"],
            "text_margin": default_mask_parameters[self.face_ids[1]]["text_margin"]
            }
        t_frame_trans = pya.DTrans(pya.DPoint(10000, 0)) * pya.DTrans.M90
        self.produce_frame(t_frame_parameters, t_frame_trans)

        self.produce_default_connectors_and_launchers()
        if self.with_gnd_bumps:
            self._produce_ground_bumps()

    def _produce_ground_bumps(self):
        """Produces ground bumps between bottom and top face.

        The bumps avoid ground grid avoidance on both faces.
        """

        bump = self.add_element(FlipChipConnectorDc)

        # boundary box
        bbox = bump.dbbox()

        # magic parameters
        delta_x = 100
        delta_y = 100
        edge_from_bump = 750

        p1 = pya.DPoint(self.face1_box.p1.x + edge_from_bump, self.face1_box.p1.y + edge_from_bump)
        p2 = pya.DPoint(self.face1_box.p2.x - edge_from_bump, self.face1_box.p2.y - edge_from_bump)

        # array size for bump creation
        n = (p2 - p1).x / delta_x
        m = (p2 - p1).y / delta_y

        avoidance_layer_bottom = pya.Region(
            self.cell.begin_shapes_rec(self.get_layer("ground grid avoidance"))).merged()
        avoidance_layer_top = pya.Region(
            self.cell.begin_shapes_rec(self.get_layer("ground grid avoidance", 1))).merged()
        avoidance_layer = avoidance_layer_bottom + avoidance_layer_top
        count = 0
        for i in range(int(n)):
            for j in range(int(m)):
                pos_bump = p1 + pya.DPoint(i * delta_x, j * delta_y)
                loc_box = pya.Region(bbox.to_itype(self.layout.dbu)).move(
                    pya.DVector(pos_bump).to_itype(self.layout.dbu))
                if loc_box.interacting(avoidance_layer.merged()).is_empty():
                    self.insert_cell(bump, pya.DTrans(pos_bump))
                    count += 1
        print("%s: Number of ground bumps %i" %(self.display_name ,count))
        self.number_of_gnd_bumps = count

    def produce_ground_grid(self):
        """Produces ground grid on t and b faces."""
        for face_id, box in enumerate([self.box, self.face1_box]):
            self.produce_ground_on_face_grid(box, face_id)

    def merge_layout_layers(self):
        """Merges layers on t and b faces."""
        for i in range(int(2)):
            self.merge_layout_layers_on_face(self.face(i))

    def produce_default_connectors_and_launchers(self, launchers_type=""):
        """Produces default connectors, launchers and routing waveguides.

        Produces launchers in face 0, connectors between faces 0 and 1, and default routing waveguides from the
        launchers to the connectors.

        Args:
            launchers_type: String determining the arrangement of launchers, "SMA8" | "ARD24", no launchers if empty
                string or unknown name

        """
        connector_positions = self._produce_connectors(launchers_type)
        if launchers_type == "SMA8":
            launchers = self.produce_launchers_SMA8()
            if self.routing_waveguides:
                self._produce_default_routing_sma8(launchers, connector_positions)
        elif launchers_type == "ARD24":
            launchers = self.produce_launchers_ARD24()
            if self.routing_waveguides:
                self._produce_default_routing_ard24(launchers, connector_positions)

    def _produce_connectors(self, launchers_type):
        # the connector ids increase from left to right and from top to bottom
        side_length = 5000
        x_step = side_length / 4
        y_step = side_length / 6
        top_left = pya.DPoint(5000 - side_length / 2 + x_step / 2, 5000 + side_length / 2 - y_step / 2)

        # ids of the subset of 24-port connectors which are also 8-port connectors
        sma8_ids = [1, 2, 4, 7, 16, 19, 21, 22]
        # dictionary where keys are connector ids, and values are the connector positions
        connectors = {}
        for i in range(4):
            for j in range(6):
                connector_id = i + j * 4
                if launchers_type == "ARD24" or (launchers_type == "SMA8" and connector_id in sma8_ids):
                    cell = self.add_element(FlipChipConnectorDc)
                    pos = top_left + pya.DPoint(i * x_step, -j * y_step)
                    connectors[connector_id] = pos
                    self.insert_cell(cell, pya.DTrans(pos), connector_id)
        return connectors

    def _produce_default_routing_sma8(self, launchers, connectors):

        l = {key: value[0] for key, value in launchers.items()}
        c = connectors
        dist1 = (l["NW"].y - c[1].y) / 2
        dist2 = (l["EN"].x - c[7].x) / 2
        paths = [
            [l["NW"], l["NW"] + pya.DPoint(0, -dist1), c[1] + pya.DPoint(0, dist1), c[1]],
            [l["NE"], l["NE"] + pya.DPoint(0, -dist1), c[2] + pya.DPoint(0, dist1), c[2]],
            [l["WN"], l["WN"] + pya.DPoint(dist2, 0), c[4] + pya.DPoint(-dist2, 0), c[4]],
            [l["EN"], l["EN"] + pya.DPoint(-dist2, 0), c[7] + pya.DPoint(dist2, 0), c[7]],
            [l["WS"], l["WS"] + pya.DPoint(dist2, 0), c[16] + pya.DPoint(-dist2, 0), c[16]],
            [l["ES"], l["ES"] + pya.DPoint(-dist2, 0), c[19] + pya.DPoint(dist2, 0), c[19]],
            [l["SW"], l["SW"] + pya.DPoint(0, dist1), c[21] + pya.DPoint(0, -dist1), c[21]],
            [l["SE"], l["SE"] + pya.DPoint(0, dist1), c[22] + pya.DPoint(0, -dist1), c[22]],
        ]
        for path in paths:
            self.insert_cell(WaveguideCoplanar, path=pya.DPath(path, 0))

    def _produce_default_routing_ard24(self, launchers, connectors):

        l = {key: value[0] for key, value in launchers.items()}
        c = connectors
        dx1 = pya.DPoint(625, 0)
        dx2 = pya.DPoint(400, 0)
        dx3 = pya.DPoint(1200, 0)
        dx4 = pya.DPoint(900, 0)
        dy1 = pya.DPoint(0, 1400)
        dy2 = pya.DPoint(0, 800)
        dy3 = pya.DPoint(0, 400)
        paths = [
            # paths for top and bottom launchers

            [l["0"], l["0"] - dy1, pya.DPoint((c[9] - dx1).x, (l["0"] - dy1).y), c[9] - dx1, c[9]],
            [l["5"], l["5"] - dy1, pya.DPoint((c[10] + dx1).x, (l["5"] - dy1).y), c[10] + dx1, c[10]],
            [l["17"], l["17"] + dy1, pya.DPoint((c[13] - dx1).x, (l["17"] + dy1).y), c[13] - dx1, c[13]],
            [l["12"], l["12"] + dy1, pya.DPoint((c[14] + dx1).x, (l["12"] + dy1).y), c[14] + dx1, c[14]],

            [l["1"], l["1"] - dy2, pya.DPoint(c[1].x, (l["1"] - dy2).y), c[1]],
            [l["4"], l["4"] - dy2, pya.DPoint(c[2].x, (l["4"] - dy2).y), c[2]],
            [l["16"], l["16"] + dy2, pya.DPoint(c[21].x, (l["16"] + dy2).y), c[21]],
            [l["13"], l["13"] + dy2, pya.DPoint(c[22].x, (l["13"] + dy2).y), c[22]],

            [l["2"], l["2"] - dy3, pya.DPoint((c[5] + dx2).x, (l["2"] - dy3).y), c[5] + dx2, c[5]],
            [l["3"], l["3"] - dy3, pya.DPoint((c[6] - dx2).x, (l["3"] - dy3).y), c[6] - dx2, c[6]],
            [l["15"], l["15"] + dy3, pya.DPoint((c[17] + dx2).x, (l["15"] + dy3).y), c[17] + dx2, c[17]],
            [l["14"], l["14"] + dy3, pya.DPoint((c[18] - dx2).x, (l["14"] + dy3).y), c[18] - dx2, c[18]],

            # paths for left and right launchers

            [l["23"], l["23"] + dx3, pya.DPoint((l["23"] + dx3).x, c[0].y), c[0]],
            [l["6"], l["6"] - dx3, pya.DPoint((l["6"] - dx3).x, c[3].y), c[3]],
            [l["18"], l["18"] + dx3, pya.DPoint((l["18"] + dx3).x, c[20].y), c[20]],
            [l["11"], l["11"] - dx3, pya.DPoint((l["11"] - dx3).x, c[23].y), c[23]],

            [l["22"], l["22"] + dx3, pya.DPoint((l["22"] + dx3).x, c[4].y), c[4]],
            [l["7"], l["7"] - dx3, pya.DPoint((l["7"] - dx3).x, c[7].y), c[7]],
            [l["19"], l["19"] + dx3, pya.DPoint((l["19"] + dx3).x, c[16].y), c[16]],
            [l["10"], l["10"] - dx3, pya.DPoint((l["10"] - dx3).x, c[19].y), c[19]],

            [l["21"], l["21"] + dx3, c[8] - dx4, c[8]],
            [l["8"], l["8"] - dx3, c[11] + dx4, c[11]],
            [l["20"], l["20"] + dx3, c[12] - dx4, c[12]],
            [l["9"], l["9"] - dx3, c[15] + dx4, c[15]],

        ]
        for path in paths:
            self.insert_cell(WaveguideCoplanar, path=pya.DPath(path, 0))