__author__ = 'Tom Van den Eede'
__copyright__ = 'Copyright 2018-2019, Palette2 Splicer Post Processing Project'
__credits__ = ['Tom Van den Eede',
               'Tim Brookman'
               ]
__license__ = 'GPLv3'
__maintainer__ = 'Tom Van den Eede'
__email__ = 'P2PP@pandora.be'

import p2pp.gcode as gcode
import p2pp.gcodeparser as gcodeparser
import p2pp.variables as v

solidlayer = []
emptylayer = []
filllayer = []
brimlayer = []

PURGE_SOLID = 1
PURGE_EMPTY = 2

current_purge_form = PURGE_SOLID
current_purge_index = 0
purge_width = 999
purge_height = 999

sequence_length_solid = 0
sequence_length_empty = 0
sequence_length_brim = 0

last_posx = None
last_posy = None

last_brim_x = None
last_brim_y = None


def if_defined(x, y):
    if x:
        return x
    return y


def calculate_purge(movelength):
    ## Assuming the extrusion is a near rectangular
    ## Volume = extrusion_length * extrusion_width * layer_height
    ## volume --> length by dividing by 1.75mm filament surface
    ##############################################################
    volume = v.extrusion_width * v.layer_height * (abs(movelength) + v.layer_height)
    return gcodeparser.filament_volume_to_length(volume)


def generate_rectangle(result, x, y, w, h):
    ew = v.extrusion_width
    x2 = x + w
    y2 = y + h
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}".format(x, y)))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x2, y, calculate_purge(w))))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x2, y2, calculate_purge(h))))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x, y2, calculate_purge(w))))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x, y, calculate_purge(h))))

    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}".format(x + ew, y + ew)))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x2 - ew, y + ew, calculate_purge(w - 2 * ew))))
    result.append(
        gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x2 - ew, y2 - ew, calculate_purge(h - 2 * ew))))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x + ew, y2 - ew, calculate_purge(w - 2 * ew))))
    result.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f} E{:.4f}".format(x + ew, y + ew, calculate_purge(h - 2 * ew))))


def _purge_calculate_sequences_length():
    global sequence_length_solid, sequence_length_empty, sequence_length_brim

    sequence_length_solid = 0
    sequence_length_empty = 0
    sequence_length_brim = 0

    for i in solidlayer:
        if i.E:
            sequence_length_solid += i.E

    for i in emptylayer:
        if i.E:
            sequence_length_empty += i.E

    for i in brimlayer:
        if i.E:
            sequence_length_brim += i.E


def _purge_create_sequence(code, pformat, x, y, w, h, step1):
    generate_front = False

    ew = v.extrusion_width

    cw = w - 4 * ew

    start1 = x + 2 * ew + (cw % step1) / 2
    end1 = x + 2 * ew + cw - (cw % step1) / 2

    start2 = y + 2 * ew - ew * 0.15
    end2 = y + h - 2 * ew + ew * 0.15

    code.append(gcode.GCodeCommand(pformat.format(start1, start2)))
    pformat = (pformat + " E{:.4f}")

    while start1 < end1:
        if generate_front:
            code.append(gcode.GCodeCommand(pformat.format(start1, start2, calculate_purge(step1))))
        else:
            generate_front = True

        code.append(gcode.GCodeCommand(pformat.format(start1, end2, calculate_purge(end2 - start2))))
        start1 += step1

        if start1 < end1:
            code.append(gcode.GCodeCommand(pformat.format(start1, end2, calculate_purge(step1))))
            code.append(gcode.GCodeCommand(pformat.format(start1, start2, calculate_purge(end2 - start2))))
        start1 += step1



def purge_create_layers(x, y, w, h):
    global solidlayer, emptylayer, filllayer

    solidlayer = []
    emptylayer = []
    filllayer = []

    ew = v.extrusion_width

    w = int(w / ew) * ew
    h = int(h / ew) * ew

    solidlayer.append(gcode.GCodeCommand(";---- SOLID WIPE -------"))
    generate_rectangle(solidlayer, x, y, w, h)

    emptylayer.append(gcode.GCodeCommand(";---- EMPTY WIPE -------"))
    generate_rectangle(emptylayer, x, y, w, h)

    filllayer.append(gcode.GCodeCommand(";---- FILL LAYER -------"))
    generate_rectangle(filllayer, x, y, w, h)

    _purge_create_sequence(solidlayer, "G1 X{:.3f} Y{:.3f}", x, y, w, h, ew)
    _purge_create_sequence(emptylayer, "G1 Y{:.3f} X{:.3f}", y, x, h, w, 2)
    _purge_create_sequence(filllayer, "G1 Y{:.3f} X{:.3f}", y, x, h, w, 15)

    _purge_generate_tower_brim(x, y, w, h)

    _purge_calculate_sequences_length()


def _purge_number_of_gcodelines():
    if current_purge_form == PURGE_SOLID:
        return len(solidlayer)
    else:
        return len(emptylayer)


def _purge_update_sequence_index():
    global current_purge_form, current_purge_index

    current_purge_index = (current_purge_index + 1) % _purge_number_of_gcodelines()
    if current_purge_index == 0:
        if (v.purgelayer + 1) * v.layer_height < v.current_position_z:
            current_purge_form = PURGE_EMPTY
        else:
            current_purge_form = PURGE_SOLID
        v.purgelayer += 1
        if v.side_wipe_length > 0:
            v.processed_gcode.append("G1 Z{:.2f} F10800\n".format((v.purgelayer + 1) * v.layer_height))
            setwipespeed()

def _purge_get_nextcommand_in_sequence():
    if current_purge_form == PURGE_SOLID:
        return solidlayer[current_purge_index]
    else:
        return emptylayer[current_purge_index]


def _purge_generate_tower_brim(x, y, w, h):
    global brimlayer, last_brim_x, last_brim_y

    ew = v.extrusion_width
    brimlayer = []
    y -= ew
    w += ew
    h += 2 * ew

    brimlayer.append(gcode.GCodeCommand("G0 X{:.3f} Y{:.3f} F4000".format(x, y)))
    brimlayer.append(gcode.GCodeCommand("G0 Z{:.3f}".format(v.layer_height)))

    for i in range(4):
        brimlayer.append(
            gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}  E{:.4f} F{}".format(x + w, y, calculate_purge(w), 1200)))
        brimlayer.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}  E{:.4f}".format(x + w, y + h, calculate_purge(h))))
        x -= ew
        w += 2 * ew
        brimlayer.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}  E{:.4f}".format(x, y + h, calculate_purge(w))))
        y -= ew
        h += 2 * ew
        brimlayer.append(gcode.GCodeCommand("G1 X{:.3f} Y{:.3f}  E{:.4f}".format(x, y, calculate_purge(h))))


def retract(tool):
    if not v.use_firmware_retraction:
        length = v.retract_length[tool]
        v.processed_gcode.append("G1 E-{:.2f}\n".format(v.retract_length[tool]))
        v.total_material_extruded -= length
        v.material_extruded_per_color[v.current_tool] -= length
        v.retraction -= length
    else:
        v.processed_gcode.append("G10\n")
        v.retraction -= 1


def unretract(tool):
    if not v.use_firmware_retraction:
        length = v.retract_length[tool]
        v.processed_gcode.append("G1 E{:.2f}\n".format(v.retract_length[tool]))
        v.total_material_extruded += length
        v.material_extruded_per_color[v.current_tool] += length
    else:
        v.processed_gcode.append("G11\n")
    v.retraction = 0


def setwipespeed():
    if (v.purgelayer == 0):
        # first purge layer prints at 1200
        v.processed_gcode.append("G1 F{}\n".format(min(1200, v.wipe_feedrate)))
    else:
        v.processed_gcode.append("G1 F{}\n".format(v.wipe_feedrate))

def purge_generate_sequence():
    global last_posx, last_posy

    if not v.side_wipe_length > 0:
        return

    actual = 0
    expected = v.side_wipe_length

    v.processed_gcode.append("; --------------------------------------------------\n")
    v.processed_gcode.append("; --- P2PP WIPE SEQUENCE START  FOR {:5.2f}mm\n".format(v.side_wipe_length))
    v.processed_gcode.append(
        "; --- DELTA = {:.2f}\n".format(v.current_position_z - (v.purgelayer + 1) * v.layer_height))

    if v.previous_tool != -1:
        index = v.previous_tool * 4 + v.current_tool
        if v.side_wipe_length > v.wiping_info[index]:
            v.side_wipe_length = v.wiping_info[index]
            v.processed_gcode.append(
                "; --- CORRECTED PURGE TO TRANSITION LENGTH {:.2f}mm\n".format(v.wiping_info[index]))
    v.processed_gcode.append("; --------------------------------------------------\n")


    v.max_tower_delta = max(v.max_tower_delta, v.current_position_z - (v.purgelayer + 1) * v.layer_height)
    v.min_tower_delta = min(v.min_tower_delta, v.current_position_z - (v.purgelayer + 1) * v.layer_height)

    if last_posx and last_posy:
        if v.retraction == 0:
            retract(v.current_tool)
        v.processed_gcode.append("G1 X{} Y{} \n".format(last_posx, last_posy))
        v.processed_gcode.append("G1 Z{:.2f} F10800\n".format((v.purgelayer + 1) * v.layer_height))
        unretract(v.current_tool)
    setwipespeed()
    # generate wipe code
    while v.side_wipe_length > 0:
        next_command = _purge_get_nextcommand_in_sequence()
        last_posx = if_defined(next_command.X, last_posx)
        last_posy = if_defined(next_command.Y, last_posy)
        v.side_wipe_length -= if_defined(next_command.E, 0)
        actual += if_defined(next_command.E, 0)
        next_command.issue_command()
        _purge_update_sequence_index()

    # return to print height
    v.processed_gcode.append("; -------------------------------------\n")
    if v.retraction == 0:
        retract(v.current_tool)
    v.processed_gcode.append("G1 Z{:.2f} F10800\n".format(v.current_position_z))
    v.processed_gcode.append("; --- P2PP WIPE SEQUENCE END DONE\n")
    v.processed_gcode.append("; -------------------------------------\n")

    # if we extruded more we need to account for that in the total count

    correction = (actual - expected) * v.extrusion_multiplier * v.extrusion_multiplier_correction
    v.total_material_extruded += correction
    v.material_extruded_per_color[v.current_tool] += correction
    v.side_wipe_length = 0
    v.retract_x = last_posx
    v.retract_y = last_posy
