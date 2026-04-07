def fix_plate(plate):

    if len(plate) < 6:
        return plate

    plate = list(plate)

    digit_to_letter = {'0':'O','1':'I','5':'S','8':'B'}
    letter_to_digit = {'O':'0','I':'1','S':'5','B':'8'}

    if plate[0] in digit_to_letter:
        plate[0] = digit_to_letter[plate[0]]

    for i in range(1,4):
        if plate[i] in letter_to_digit:
            plate[i] = letter_to_digit[plate[i]]

    for i in range(4,6):
        if plate[i] in digit_to_letter:
            plate[i] = digit_to_letter[plate[i]]

    for i in range(6,len(plate)):
        if plate[i] in letter_to_digit:
            plate[i] = letter_to_digit[plate[i]]

    return "".join(plate)