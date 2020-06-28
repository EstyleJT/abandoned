#!/usr/bin/env python3

"""
A single file script to implement 2048 game with extended features. (by estylejt@hotmail.com)

    Prerequisites:
        Python3 with standard library if it is a plain .py file
        Unblocked TCP port 80 if it runs as a game server

    Features:
        Run in server mode
        Or run in console mode
        Attacker is available to play as
        Board shape is customizable
        Endgame is possible to play
        Robot is available to battle against
        Human player is available to battle against
        Logging

    Usage:
        To run it in server mode, just simply:
            python3 2048.py
            or to run it in background on linux, use:
                nohup python3 2048.py &
            or on windows, use:
                start /b python3 2048.py
            and visit this URL to access a web client:
                http://<your_ip_or_hostname>/
            to shut it down, press CTRL+C or use KILL or TASKMGR

        To run it in console mode, add --localonly as:
            python3 2048.py --localonly
            to shut it down, press CTRL+C

        ATTENTION: CASE SENSITIVE
        Complete usage:
            python3 2048.py [--localonly[=auto]]
                            [--board_shape=<board_shape>] [--board_tiles=<board_tiles>]
                            [--attacker_type=<attacker_type>] [--defender_type=<attacker_type>]
            Explanation:
                --localonly=auto    it disables Manual player and console interaction,
                                    it is useful to test robot players

                parameters below are working only in console mode:
                --board_shape       default is [4,4] which presents a usual game board
                --board_tiles       default is [] which presents an empty board,
                                    this parameter is prior to board_shape,
                                    it is useful to load an endgame
                --attacker_type     default is Random in both modes, see below for more details
                --attacker_type     default is Manual in console mode, Online in server mode,
                                    see below for more details

            Possible Player Type:
                attacker_type:      it is the player who places new number 2 or 4 occasionally
                    Random          literally, who acts the same as in a usual game
                    Manual          only available in console mode
                    Online          only available in server mode, see below
                    Strategy        better replacement of random attacker
                defender_type:      it is the player who moves the tiles as in a usual game
                    Random          literally
                    Manual          only available in console mode
                    Online          only available in server mode, see below
                    Strategy        better replacement of random defender

    Online play:
        When it runs in server mode, a web application is exposed at:
            http://<your_ip_or_hostname>/<QUERYSTRING>
        Communication is through requests with proper QUERYSTRING and response is JSON.

        To start a new game, request:
            http://<your_ip_or_hostname>/?start=new
            It will start a new game with default parameters as:
                board_shape=[4,4]
                board_tiles=[]
                attacker_type=Random
                defender_type=Online
                These four parameters can be appended to QUERYSTRING to customize new game.
                At least one Online player must be present.
                Manual player is not allowed because it's for console mode only.
            A JSON message will be responded such as:
                {"uuid": "<one_36_characters_uuid>", "message": "A new game might have started"}
                THE UUID IS IMPORTANT!

        To get details, request:
            http://<your_ip_or_hostname>/?display&uuid=<one_36_characters_uuid>
            The attacker_wait and defender_wait indicate who is about to play when it's True.
            When they are False, the game might have ended, but exception exists.
            The game is truly ended if round_score is not -1 and two wait-signals are both False.

        When attacker_wait is True, to play it, request:
            http://<your_ip_or_hostname>/?attack=<location>&uuid=<one_36_characters_uuid>
            The location is a comma separated string such as attack=1,3
            attack=1,3 indicates to place a number at tiles[1][3], it is zero based.
            The new number to be placed will be 2 or occasionally 4 with 10% chance.
            To surrender, use attack=giveup

        When defender_wait is True, to play it, request:
            http://<your_ip_or_hostname>/?defend=<dimension,direction>&uuid=<one_36_characters_uuid>
            It indicates at which axis you want to move and to which direction.
            Dimension is zero based, direction is either -1 or 1, -1 means approaching the origin point.
            For example, defend=1,1 means move the 2nd axis away from the origin point.
            To surrender, use defend=giveup

        To get a random unoccupied game, request:
            http://<your_ip_or_hostname>/?get_an_unoccupied_game
            Unoccupied games are those games which:
                attacker_type=Online and defender_type=Online
                and an unoccupied_role is explicitly given when request new game
                and the URL of the invitation of this new game is not visited

        Meanwhile, it provides a simple web client here:
            http://<your_ip_or_hostname>/
"""

import random
import json
import sys
import wsgiref.simple_server as wsgi
import threading
import queue
import os
from copy import deepcopy
from datetime import datetime
from time import sleep
from uuid import uuid4
from math import log
from urllib.parse import unquote

class Board():
    """
    core class to represent a game board with necessary playing methods.

    key properties:
        __shape     tuple, visit by get_shape(), it cannot be changed after initialization
        __tiles     list, visit by get_tiles(), it can be changed only by move() or place()

    key methods:
        __init__()  to initialize an empty board or load an endgame
        place()     boolean, attacker's action
        move()      boolean, defender's action

    Board class does not manage the play flow and life cycle
    Because the shape of board is customizable, not limited to 2D 4*4,
    the code is a little bit trickier in order to adapt variable dimension board
    """
    def __init__(self,shape=(4,4),*,load_tiles=[]):
        """when load_tiles is provided properly, shape will be ignored"""
        if type(load_tiles) is list and len(load_tiles)>0:
            if len(str(load_tiles))>200: raise Exception("Size of load_tiles is too large")
            def validate_tiles(tiles,depth=0,max_depth=-1,dims_length={}):
                if depth not in dims_length:
                    dims_length[depth]=len(tiles)
                elif dims_length[depth]!=len(tiles):
                    raise Exception("Shape of load_tiles is not regular")
                for sub_tiles in tiles:
                    if type(sub_tiles) is list:
                        if len(sub_tiles)>0:
                            depth=depth+1
                            depth,max_depth,dims_length=validate_tiles(sub_tiles,depth,max_depth,dims_length)
                        else:
                            raise Exception("Empty tile is not allowed")
                    elif type(sub_tiles) is int:
                        if max_depth==-1: max_depth=depth
                        if max_depth!=depth:
                            raise Exception("Shape of load_tiles is not regular")
                        elif sub_tiles<0 or sub_tiles>0 and log(sub_tiles,2)%1!=0:
                            raise Exception("At least one tile in load_tiles is not an appropriate number")
                        continue
                    else:
                        raise Exception("load_tiles has something wrong")
                depth=depth-1
                return depth,max_depth,dims_length
            validate_tiles(load_tiles) ### recursively validate the load_tiles
            self.__shape=()
            def recursive_len(tiles):
                self.__shape=self.__shape+tuple([len(tiles)])
                if type(tiles[0])==list:
                    recursive_len(tiles[0])
            recursive_len(load_tiles) ### recursively load __shape property
            self.__tiles=deepcopy(load_tiles)
        else:
            if type(shape) is not tuple or len(shape)==0:
                raise Exception("Shape is not properly specified")
            elif len(shape)>4:
                raise Exception("Shape is not allowed to be more than 4 dimensions")
            else:
                for dim_length in shape:
                    if type(dim_length) is not int:
                        raise Exception("Shape is not properly specified")
                    elif dim_length<2 or dim_length>10:
                        raise Exception("Shape is too small or too large")
            self.__shape=tuple(shape)
            tile=0
            for dim in range(len(self.__shape)-1,-1,-1): ### fill zero from inside out (inverted order)
                tile=[deepcopy(tile) for count in range(self.__shape[dim])]
            self.__tiles=tile

    def get_tiles(self):
        return self.__tiles

    def get_shape(self):
        return self.__shape

    def __get_tile(self,location):
        tile=self.__tiles
        for dim in range(len(location)):
            tile=tile[location[dim]]
        return tile

    def __set_tile(self,location,number):
        """list is a by-ref object, use this feature to set a tile number"""
        tile=self.__tiles
        for dim in range(len(location)-1):
            tile=tile[location[dim]]
        tile[location[-1]]=number

    def __generate_sequential_coordinates(self,dimension,direction):
        """
        prepare a ordered set of tiles to move one by one

        the order is not unique
        any order will be valid if the direction on the specific dimension is complied
        for example with a 3*3 board:
            0   2   0
            0   0   8
            4   4   4
        supposing the movement is to left
        it doesn't mantter which row moves first
        it only does matter, in each row, which column moves first, the leftmost one
        so, this method use little math to ensure the order
        """
        tile_count=1
        for dim_length in self.__shape:
            tile_count=tile_count*dim_length ### figure out how many tiles in total
        sequential_coordinates=[]
        for traversal in range(tile_count):
            sequential_coordinates.append([0 for count in range(len(self.__shape))])
            ### fill sequential_coordinates with zero at first
        fraction=tile_count
        ### for example, shape is (3,3), tile_count is 9
        ### sequential_coordinates is [[0,0],[0,0],[0,0],[0,0],[0,0],[0,0],[0,0],[0,0],[0,0]]
        ### move dimension is 1, direction is 1, in short, move right
        for dim,dim_length in enumerate(self.__shape):
            fraction=fraction//dim_length
            ### for the first cycle, fraction is 9/3=3
            ### and then, fraction is 3/3=1
            for index_coordinate,coordinate in enumerate(sequential_coordinates):
                ### since sequential_coordinates is a by-ref list,
                ### changes to coordinate will be applied to sequential_coordinates itself
                ### for the first outter cycle, fraction is 3
                if direction==-1 or dimension!=dim:
                    ### when the direction is approaching origin (be -1)
                    ### or current dimension is not the dimension to be moved
                    ### coordinate of current dimension is filled incrementally from zero
                    coordinate[dim]=index_coordinate//fraction%dim_length
                    ### for the first outter cycle
                    ### coordinate[0]=(0~8)//3%3=0,0,0,1,1,1,2,2,2
                    ### sequential_coordinates is:
                    ### [[0,0],[0,0],[0,0],[1,0],[1,0],[1,0],[2,0],[2,0],[2,0]]
                else:
                    ### otherwise, it is filled decrementally to zero
                    coordinate[dim]=dim_length-1-index_coordinate//fraction%dim_length
                    ### for the second otter cycle
                    ### coordinate[1]=3-1-(0~8)//1%3=2,1,0,2,1,0,2,1,0
                    ### sequential_coordinates is:
                    ### [[0,2],[0,1],[0,0],[1,2],[1,1],[1,0],[2,2],[2,1],[2,0]]
                    ### everything is in order now
        return sequential_coordinates

    def move(self,dimension,direction):
        """
        move the tiles at specific dimension (or axis) to specific direction

        parameters:
            dimension   required, int, zero based, must be within in the shape
            direction   required, -1 or 1, -1 means approaching the origin

        return:
            boolean     True if at least one tile is moved, otherwise False

        remarks:
            steps is calculated internally but is not exposed by now.
            according to the observed game rules, merging combo is not allowed,
            for example, movement of 4,4,4,4 to left results 8,8,0,0, not 16,0,0,0
            so the blocked_coordinates is introduced.
        """
        if type(dimension) is not int or (not 0<=dimension<len(self.__shape)):
            return False
        elif direction not in (-1,1):
            return False
        def move_tile(coordinate,dimension,direction):
            """
            recursive function to move a tile until it cannot be moved any more

            the outmost call of this function is according to sequential_coordinates
            the inner recursive call is one step each time
            recursion occurs when the move target is zero, so the further move is expecting
            """
            steps=0
            if coordinate[dimension]==(0 if direction==-1 else self.__shape[dimension]-1):
                return 0
            source=self.__get_tile(coordinate)
            if source==0:
                return 0
            target_coordinate=coordinate.copy()
            target_coordinate[dimension]=target_coordinate[dimension]+direction
            if target_coordinate in blocked_coordinates:
                ### blocked_coordinates is defined outside the funcion
                return 0
            target=self.__get_tile(target_coordinate)
            if source==target:
                self.__set_tile(target_coordinate,target*2)
                self.__set_tile(coordinate,0)
                steps=steps+1
                blocked_coordinates.append(target_coordinate)
            elif target==0:
                self.__set_tile(target_coordinate,source)
                self.__set_tile(coordinate,0)
                steps=steps+1
                steps=steps+move_tile(target_coordinate,dimension,direction)
            return steps
        sequential_coordinates=self.__generate_sequential_coordinates(dimension,direction)
        blocked_coordinates=[]
        steps=0
        for coordinate in sequential_coordinates:
            steps=steps+move_tile(coordinate,dimension,direction)
        return steps>0

    def place(self,location):
        """
        place a new number onto a specific tile, the number is 2 or 4 with 10% chance

        parameters:
            location    required, list, for example, [1,2] represents tiles[1][2]

        return:
            boolean     True if the number is placed, otherwise False
        """
        if len(location)!=len(self.__shape):
            return False
        for index in range(len(location)):
            if type(location[index]) is not int:
                return False
            elif (not 0<=location[index]<self.__shape[index]):
                return False
        if self.__get_tile(location)==0:
            self.__set_tile(location,2 if random.randint(0,9)<9 else 4)
            return True
        else:
            return False


class Base_Attacker():
    """
    any attacker class implemented in this script must derive from this base class

    attacker never manipulates the board directly
    attacker gets an image of board tiles, figures out what to do, tells it to round instance only
    the base attacker class:
        gets a uuid from the round instance, online attacker uses it
        exposes get_place_instruction() to call think() which implemented in child class
    so that any child class only cares about think() method, for simplicity
    """
    def __init__(self,round_uuid):
        self.uuid=round_uuid ### uuid is set in round.start() when initialize an attacker
    def get_round_uuid(self):
        return self.uuid
    def think(self,tiles):
        return {"keepgoing":False,"location":None}
    def get_place_instruction(self,tiles):
        place_instruction=self.think(tiles)
        if type(place_instruction) is not dict:
            raise Exception("place_instruction is not a dictionary")
        elif len(place_instruction)!=2:
            raise Exception("place_instruction does not have two members only")
        elif "keepgoing" not in place_instruction or "location" not in place_instruction:
            raise Exception("place_instruction does not have expected members")
        elif type(place_instruction["keepgoing"]) is not bool:
            raise Exception("place keepgoing is not a bool")
        elif place_instruction["keepgoing"]:
            if type(place_instruction["location"]) is not list:
                raise Exception("place location is not a list")
                for dim in place_instruction["location"]:
                    if dim is not int:
                        raise Exception("place location is not properly specified")
        return place_instruction

class Random_Attacker(Base_Attacker):
    """
    find out all zero tiles and return one randomly

    random attacker acts the same as a usual game
    it's the default attacker type in both server mode and console mode
    """
    def think(self,tiles):
        def find_zero_tiles(tiles,coordinate=[],zero_tiles=[]):
            for index,sub_tiles in enumerate(tiles):
                coordinate.append(index)
                if type(sub_tiles) is list:
                    find_zero_tiles(sub_tiles,coordinate,zero_tiles)
                else:
                    if sub_tiles==0:
                        zero_tiles.append(coordinate.copy())
                coordinate.pop()
            return zero_tiles
        zero_tiles=find_zero_tiles(tiles)
        if len(zero_tiles)>0:
            return {"keepgoing":True,"location":random.choice(zero_tiles)}
        else:
            return {"keepgoing":False,"location":None}

class Manual_Attacker(Base_Attacker):
    """
    manually specify a location to place a new number

    manual attacker is not allowed in server mode
    manual attacker is not allowed in console mode when --localonly=auto
    """
    def think(self,tiles):
        print("Current Board:")
        print(tiles)
        keepgoing=False
        location=None
        while True: ### jump out when player gives up or provides comma separated integers
            input_valid_flag=True
            location=[]
            input_location=input("To which tile do you want to place number: ").strip()
            if input_location=="giveup":
                print("Attacker gives up")
                keepgoing=False
                break
            splitted_location=input_location.split(",")
            for each_location_element in splitted_location:
                if not each_location_element.isnumeric():
                    input_valid_flag=False
                    break
                else:
                    location.append(int(each_location_element))
            if input_valid_flag:
                keepgoing=True
                break
            else:
                print("Invalid place location: ",input_location)
        return {"keepgoing":keepgoing,"location":location}

class Online_Attacker(Base_Attacker):
    """
    online attacker works with Server.ONLINE_ROUNDS

    parameter tiles in think() is useless
    it works like this:
        Server class listens to HTTP request and store them into Server.ONLINE_ROUNDS
        online attacker interacts with Server.ONLINE_ROUNDS
            when the timing is right, it sends out a signal (attacker_wait=true) and waits for instruction
            new proper HTTP request provides an instruction and shuts down the wait signal
            online attacker stops waiting and returns the instruction
        timing is managed by round instance
    """
    def think(self,tiles):
        round_uuid=self.get_round_uuid()
        if round_uuid not in Server.ONLINE_ROUNDS:
            sys.exit("round_uuid is not in Server.ONLINE_ROUNDS")
        Server.ONLINE_ROUNDS[round_uuid]["board_tiles"]=tiles
        Server.ONLINE_ROUNDS[round_uuid]["attacker_wait"]=True
        while Server.ONLINE_ROUNDS[round_uuid]["attacker_wait"]:
            sleep(0.1)
        Server.ONLINE_ROUNDS[round_uuid]["last_update"]=datetime.now()
        return Server.ONLINE_ROUNDS[round_uuid]["attacker_instruction"]

class Strategy_Attacker(Base_Attacker):
    """
    it's a better replacement of random attacker to increase difficulty of defend play
    """
    def think(self,tiles):
        tiles_location={}
        def recursive_tile(tiles,coordinate=[]):
            for index,sub_tiles in enumerate(tiles):
                coordinate.append(index)
                if type(sub_tiles) is list:
                    recursive_tile(sub_tiles,coordinate)
                else:
                    tiles_location.setdefault(sub_tiles,[]).append(coordinate.copy())
                coordinate.pop()
        recursive_tile(tiles)
        possible_zeros=[]
        if 0 in tiles_location:
            sorted_numbers=list(tiles_location.keys())
            sorted_numbers.sort(reverse=True)
            def is_adjoining(location_a,location_b):
                adjoining_dims_count=0
                for index in range(len(location_a)):
                    if abs(location_a[index]-location_b[index])==1:
                        adjoining_dims_count=adjoining_dims_count+1
                    elif abs(location_a[index]-location_b[index])>1:
                        return False
                if adjoining_dims_count==1:
                    return True
                else:
                    return False
            for greatest_number in sorted_numbers:
                for greatest_tile in tiles_location[greatest_number]:
                    for zero_tile in tiles_location[0]:
                        if is_adjoining(greatest_tile,zero_tile):
                            possible_zeros.append(tuple(zero_tile))
                if len(possible_zeros)>0: break
            possible_zeros=list({}.fromkeys(possible_zeros).keys())
        if len(possible_zeros)>0:
            return {"keepgoing":True,"location":list(random.choice(possible_zeros))}
        else:
            return {"keepgoing":False,"location":None}


class Base_Defender():
    """
    any defender class implemented in this script must derive from this base class

    defender never manipulates the board directly
    defender gets an image of board tiles, figures out what to do, tells it to round instance only
    the base defender class:
        gets a uuid from the round instance, online defender uses it
        exposes get_move_instruction() to call think() which implemented in child class
    so that any child class only cares about think() method, for simplicity
    """
    def __init__(self,round_uuid): ### uuid is set in round.start() when initialize an defender
        self.uuid=round_uuid
    def get_round_uuid(self):
        return self.uuid
    def think(self,tiles):
        return {"keepgoing":False,"dimension":None,"direction":None}
    def get_move_instruction(self,tiles):
        move_instruction=self.think(tiles)
        if type(move_instruction) is not dict:
            raise Exception("move_instruction is not a dictionary")
        elif len(move_instruction)!=3:
            raise Exception("move instruction does not have three members only")
        elif "keepgoing" not in move_instruction or "dimension" not in move_instruction or "direction" not in move_instruction:
            raise Exception("move instruction does not have expected members")
        elif type(move_instruction["keepgoing"]) is not bool:
            raise Exception("move keepgoing is not a bool")
        elif move_instruction["keepgoing"]:
            if type(move_instruction["dimension"]) is not int:
                raise Exception("move dimension is not a number")
            elif move_instruction["direction"] not in (-1,1):
                raise Exception("move direction is neither -1 nor 1")
        return move_instruction

class Random_Defender(Base_Defender):
    """
    find out all possible movements and return one randomly
    """
    def think(self,tiles):
        def recursive_dims(tiles,dims=0):
            if type(tiles) is list:
                dims=dims+1
                dims=recursive_dims(tiles[0],dims)
            return dims
        dims=recursive_dims(tiles)
        possible_moves=[]
        for dim in range(dims):
            if (Board(load_tiles=tiles)).move(dim,-1):possible_moves.append([dim,-1])
            if (Board(load_tiles=tiles)).move(dim,1):possible_moves.append([dim,1])
        if len(possible_moves)>0:
            decided_move=random.choice(possible_moves)
            return {"keepgoing":True,"dimension":decided_move[0],"direction":decided_move[1]}
        else:
            return {"keepgoing":False,"dimension":None,"direction":None}

class Manual_Defender(Base_Defender):
    """
    manually specify the dimension and direction to move

    it's the default defender type in console mode
    manual defender is not allowed in server mode
    manual defender is not allowed in console mode when --localonly=auto
    """
    def think(self,tiles):
        print("Current Board:")
        print(tiles)
        keepgoing=False
        dimension=None
        direction=None
        while True: ### jump out when player gives up or provides proper dimension and direction
            input_valid_flag=True
            input_dim_and_dir=input("At which axis do you want to move and to which direction: ").strip()
            if input_dim_and_dir=="giveup":
                print("Defender gives up")
                keepgoing=False
                break
            splitted_dim_and_dir=input_dim_and_dir.split(",")
            if len(splitted_dim_and_dir)!=2:
                input_valid_flag=False
            elif not splitted_dim_and_dir[0].isnumeric():
                input_valid_flag=False
            elif not splitted_dim_and_dir[1] in ("-1","1"):
                input_valid_flag=False
            else:
                dimension=int(splitted_dim_and_dir[0])
                direction=int(splitted_dim_and_dir[1])
            if input_valid_flag:
                keepgoing=True
                break
            else:
                print("Invalid move dimension and direction: ",input_dim_and_dir)
        return {"keepgoing":keepgoing,"dimension":dimension,"direction":direction}

class Online_Defender(Base_Defender):
    """
    online defender works with Server.ONLINE_ROUNDS

    parameter tiles in think() is useless
    it works like this:
        Server class listens to HTTP request and store them into Server.ONLINE_ROUNDS
        online defender interacts with Server.ONLINE_ROUNDS
            when the timing is right, it sends out a signal (defender_wait=true) and waits for instruction
            new proper HTTP request provides an instruction and shuts down the wait signal
            online defender stops waiting and returns the instruction
        timing is managed by round instance
    """
    def think(self,tiles):
        round_uuid=self.get_round_uuid()
        if round_uuid not in Server.ONLINE_ROUNDS:
            sys.exit("round_uuid is not in Server.ONLINE_ROUNDS")
        Server.ONLINE_ROUNDS[round_uuid]["board_tiles"]=tiles
        Server.ONLINE_ROUNDS[round_uuid]["defender_wait"]=True
        while Server.ONLINE_ROUNDS[round_uuid]["defender_wait"]:
            sleep(0.1)
        Server.ONLINE_ROUNDS[round_uuid]["last_update"]=datetime.now()
        return Server.ONLINE_ROUNDS[round_uuid]["defender_instruction"]

class Strategy_Defender(Base_Defender):
    """
    it is a better replacement of random defender to increase difficulty of attack play
    """
    def think(self,tiles):
        def recursive_dims(tiles,dims=0):
            if type(tiles) is list:
                dims=dims+1
                dims=recursive_dims(tiles[0],dims)
            return dims
        dims=recursive_dims(tiles)
        for dim in range(dims):
            if (Board(load_tiles=tiles)).move(dim,-1):
                return {"keepgoing":True,"dimension":dim,"direction":-1}
        for reversed_dim in range(dims-1,-1,-1):
            if (Board(load_tiles=tiles)).move(reversed_dim,1):
                return {"keepgoing":True,"dimension":reversed_dim,"direction":1}
        else:
            return {"keepgoing":False,"dimension":None,"direction":None}


class Round():
    """
    core class to manage a round of game, interacts with both players and board

    key properties:
        __uuid                  str, works mainly in server mode for tracking online rounds
        __board_shape           tuple, pass to board
        __board_tiles           list, pass to board
        __attacker_type         str, pass to board
        __defender_type         str, pass to board

    key methods:
        start()                 int, it manages the life cycle of a game, and returns a score
        get_score()             int, for each tile, score=tile*(log(tile,2)-1), sum them up

    remarks:
        round.start() doesn't care the game mode and player type.
        it manages the gameplay itself:
            create a new game board
            ask attacker for an instruction
            execute the instruction on the board
            ask defender for an instruction
            execute the instruction on the board
            ask attacker... run in circle until player gives up
            call get_score() and return the score
    """
    def __init__(self,**round_parameters):
        self.__uuid=round_parameters.get("uuid",str(uuid4()))
        self.__board_shape=tuple(json.loads(round_parameters.get("board_shape","[4,4]")))
        self.__board_tiles=json.loads(round_parameters.get("board_tiles","[]"))
        self.__attacker_type=round_parameters.get("attacker_type","Random")
        self.__defender_type=round_parameters.get("defender_type","Manual")

    def get_uuid(self):
        return self.__uuid

    def get_score(self,tiles,score=0):
        for sub_tiles in tiles:
            if type(sub_tiles) is list:
                score=self.get_score(sub_tiles,score)
            else:
                score=score+(0 if sub_tiles==0 else sub_tiles*int(log(sub_tiles,2)-1))
        return score

    def start(self):
        try:
            board=Board(self.__board_shape,load_tiles=self.__board_tiles)
            attacker=eval(self.__attacker_type+"_Attacker('"+self.get_uuid()+"')")
            if type(attacker).__base__ is not Base_Attacker:
                Logger.log("ERROR","Attacker is not properly derived, quit by force",\
                               self.get_uuid(),\
                               {"attacker_type":self.__attacker_type}\
                          )
                sys.exit()
            defender=eval(self.__defender_type+"_Defender('"+self.get_uuid()+"')")
            if type(defender).__base__ is not Base_Defender:
                Logger.log("ERROR","Defender is not properly derived, quit by force",\
                               self.get_uuid(),\
                               {"defender_type":self.__defender_type}\
                          )
                sys.exit()
            Logger.log("INFO","New round started",\
                           self.get_uuid(),\
                           {"board_shape":board.get_shape(),\
                            "board_tiles":board.get_tiles(),\
                            "attacker_type":self.__attacker_type,\
                            "defender_type":self.__defender_type\
                           }\
                      )
        except Exception as err:
            Logger.log("ERROR","New round failed to start, quit by force",\
                           self.get_uuid(),\
                           {"ERROR_MESSAGE":str(err),\
                            "board_shape":self.__board_shape,\
                            "board_tiles":self.__board_tiles,\
                            "attacker_type":self.__attacker_type,\
                            "defender_type":self.__defender_type\
                           }\
                      )
            sys.exit()
        round_ended=False
        while round_ended==False:
            while round_ended==False:
                try:
                    attacker_instruction=attacker.get_place_instruction(board.get_tiles())
                    Logger.log("DEBUG","Attacker decided",\
                                   self.get_uuid(),\
                                   {"attacker_instruction":attacker_instruction}\
                              )
                except SystemExit as err:
                    Logger.log("ERROR","Fatal error occurred while attacker is thinking, quit by force",\
                                   self.get_uuid(),\
                                   {"ERROR_MESSAGE":str(err)}\
                              )
                    sys.exit()
                except Exception as err:
                    Logger.log("ERROR","Attacker failed to think, try to rethink",\
                                   self.get_uuid(),\
                                   {"ERROR_MESSAGE":str(err)}\
                              )
                    continue
                if not round_ended and attacker_instruction["keepgoing"]:
                    place_succeeded=board.place(attacker_instruction["location"])
                    if place_succeeded:
                        Logger.log("DEBUG","Attacker has executed the instruction",\
                                       self.get_uuid(),\
                                       {"board_tiles":board.get_tiles()}\
                                  )
                        break
                    else:
                        Logger.log("DEBUG","Attacker failed to execute the instruction",\
                                       self.get_uuid()\
                                  )
                        continue
                else:
                    Logger.log("DEBUG","Attacker surrendered, try to end this round",\
                                   self.get_uuid()\
                              )
                    round_ended=True
                    break
            while round_ended==False:
                try:
                    defender_instruction=defender.get_move_instruction(board.get_tiles())
                    Logger.log("DEBUG","Defender decided",\
                                   self.get_uuid(),\
                                   {"defender_instruction":defender_instruction}\
                              )
                except SystemExit as err:
                    Logger.log("ERROR","Fatal error occurred while defender is thinking, quit by force",\
                                   self.get_uuid(),\
                                   {"ERROR_MESSAGE":str(err)}\
                              )
                    sys.exit()
                except Exception as err:
                    Logger.log("ERROR","Defender failed to think, try to rethink",\
                                   self.get_uuid(),\
                                   {"ERROR_MESSAGE":str(err)}\
                              )
                    continue
                if not round_ended and defender_instruction["keepgoing"]:
                    move_succeeded=board.move(defender_instruction["dimension"],defender_instruction["direction"])
                    if move_succeeded:
                        Logger.log("DEBUG","Defender has executed the instruction",\
                                       self.get_uuid(),\
                                       {"board_tiles":board.get_tiles()}\
                                  )
                        break
                    else:
                        Logger.log("DEBUG","Defender failed to execute the instruction",\
                                       self.get_uuid()\
                                  )
                        continue
                else:
                    Logger.log("DEBUG","Defender surrendered, try to end this round",\
                                   self.get_uuid()\
                              )
                    round_ended=True
                    break
        round_score=self.get_score(board.get_tiles())
        Logger.log("INFO","Round ended",\
                       self.get_uuid(),\
                       {"round_score":round_score,\
                           "board_tiles":board.get_tiles()\
                       }\
                  )
        return round_score


class Server():
    """
    server class hosts a web interface and manages online game data

    key properties:
        __is_stopped                bool
        ONLINE_ROUNDS               dictionary, the structure is {uuid:{k:w,*},*}
                                                "k:w" for example:
                                                    "round":an_instance_of_round,
                                                    "board_tiles":an_list_of_tiles,
                                                    ......
                                                    "attacker_wait":true_or_false
                                                    ......
                                                    "last_update":str_of_datetime_now
                                                    ......

    key methods:
        __server_daemon()           None, it implements a web interface and its logics
        __clean_online_rounds()     None, garbage collection method with infinite loop
        serve_forever()             None, call __clean_online_rounds() and __server_daemon()

    remarks:
        server class is not allowed to initialize an instance.
    """
    __is_stopped=True
    ONLINE_ROUNDS={}

    class __class_for_hiding_console_log_only(wsgi.WSGIRequestHandler):
        def log_message(self,format,*args):
            pass

    def __init__(self):
        raise Exception("Server class is not allowed to initialize")

    @classmethod
    def __server_daemon(cls):
        def server_process(environment,response_header):
            """
            this IF block below implements a simple web client which can be accessed via:
                http://<your_ip_or_hostname>/
            or
                http://<your_ip_or_hostname>/<Attacker_or_Defender>&<one_36_characters_uuid>
            the latter one is for inviting opponent.
            """
            sleep(0.01)
            if environment["QUERY_STRING"]==""\
                and environment["PATH_INFO"]!="/favicon.ico"\
                or\
                len(environment["QUERY_STRING"].split("&"))==2\
                and environment["QUERY_STRING"].split("&")[0] in ("Attacker","Defender")\
                and len(environment["QUERY_STRING"].split("&")[1])==36:
                Logger.log("DEBUG","Page request received",\
                           "",\
                           {"REMOTE_ADDR":environment["REMOTE_ADDR"],\
                            "QUERY_STRING":str(environment["QUERY_STRING"])\
                           }\
                      )
                if len(environment["QUERY_STRING"].split("&"))==2\
                    and environment["QUERY_STRING"].split("&")[0] in ("Attacker","Defender")\
                    and environment["QUERY_STRING"].split("&")[1] in cls.ONLINE_ROUNDS\
                    and cls.ONLINE_ROUNDS[environment["QUERY_STRING"].split("&")[1]]["unoccupied_role"]==environment["QUERY_STRING"].split("&")[0]:
                    cls.ONLINE_ROUNDS[environment["QUERY_STRING"].split("&")[1]]["unoccupied_role"]=""
                status="200 OK"
                headers=[("Content-type","text/html; charset=utf-8")]
                response_header(status, headers)
                response_body=r"""
                <!DOCTYPE html>
                <html lang="en">
                <head>
                <meta charset="UTF-8"/>
                <meta name="Generator" content="EditPlus®">
                <meta name="Author" content="estylejt@hotmail.com">
                <meta name="Keywords" content="2048">
                <meta name="Description" content="A single file script to implement 2048 game with extended features. (by estylejt@hotmail.com)">
                <meta name="viewport" content="width=device-width,initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no"/>
<title>2048</title>
                <style>
                body {
                    background-color: #FAF8EF;
                    padding: 0;
                }
                #board-control {
                    text-align: center;
                    padding: 10px;
                    letter-spacing: 20px;
                }
                #board-message {
                    text-align: center;
                    padding: 10px;
                }
                #board-message>div:first-of-type {
                    color: #BBADA0;
                    font-size: small;
                }
                #board-message>div:last-of-type {
                    font-weight: bold;
                }
                #board-config {
                    text-align: center;
                    line-height: 2;
                    font-size: small;
                }
                #board-container {
                    position: relative;
                    width: 32%;
                    height: 0;
                    padding-bottom: 32%;
                    left: 0;
                    top: 0;
                    right: 0;
                    buttom: 0;
                    margin: auto;
                    border: thick solid #BBADA0;
                    background-color: #BBADA0;
                }
                #board-container>div {
                    position: absolute;
                    width: 100%;
                    height: 100%;
                    display: flex;
                    display: -webkit-flex;
                    flex-wrap: wrap;
                }
                #board-container>div>div {
                    width: 23%;
                    height: 23%;
                    overflow: hidden;
                    flex-grow: 1;
                    margin: 1%;
                    display: flex;
                    display: -webkit-flex;
                    align-items: center;
                    justify-content: center;
                }
                .tile-0, .tile-2, .tile-4, .tile-8, .tile-16, .tile-32, .tile-64 {
                    font-size: 3vw;
                }
                .tile-128, .tile-256, .tile-512 {
                    font-size: 2.8vw;
                }
                .tile-1024, .tile-2048, .tile-4096, .tile-8192 {
                    font-size: 2.6vw;
                }
                .tile-16384, .tile-32768, .tile-65536 {
                    font-size: 2.3vw;
                }
                .tile-131072 {
                    font-size: 2vw;
                }
                .tile-0 {
                    background-color: #CABFB5;
                    color: #CABFB5;
                }
                .tile-2 {
                    background-color: #EEE4DA;
                    color: #776E65;
                }
                .tile-4 {
                    background-color: #EDE0C8;
                    color: #776E65;
                }
                .tile-8 {
                    background-color: #F2B179;
                    color: #F9F6F2;
                }
                .tile-16 {
                    background-color: #F59563;
                    color: #F9F6F2;
                }
                .tile-32 {
                    background-color: #F67C5F;
                    color: #F9F6F2;
                }
                .tile-64 {
                    background-color: #F65E3B;
                    color: #F9F6F2;
                }
                .tile-128 {
                    background-color: #EDCF72;
                    color: #F9F6F2;
                }
                .tile-256 {
                    background-color: #EDCC61;
                    color: #F9F6F2;
                }
                .tile-512 {
                    background-color: #EDC850;
                    color: #F9F6F2;
                }
                .tile-1024 {
                    background-color: #EDC53F;
                    color: #F9F6F2;
                }
                .tile-2048 {
                    background-color: #EDC22E;
                    color: #F9F6F2;
                }
                .tile-4096 {
                    background-color: #3C3A32;
                    color: #F9F6F2;
                }
                .tile-8192 {
                    background-color: #1C1B17;
                    color: #F9F6F2;
                }
                .tile-16384, .tile-32768, .tile-65536, .tile-131072 {
                    background-color: red;
                    color: yellow;
                }
                @media screen and (orientation:portrait) {
                    #board-container {
                        width: 96%;
                        padding-bottom: 96%;
                    }
                    .tile-0, .tile-2, .tile-4, .tile-8, .tile-16, .tile-32, .tile-64 {
                        font-size: 9vw;
                    }
                    .tile-128, .tile-256, .tile-512 {
                        font-size: 8.4vw;
                    }
                    .tile-1024, .tile-2048, .tile-4096, .tile-8192 {
                        font-size: 7.8vw;
                    }
                    .tile-16384, .tile-32768, .tile-65536 {
                        font-size: 6.9vw;
                    }
                    .tile-131072 {
                        font-size: 6vw;
                    }
                }
                </style>
                <style>
                #board-container>div>div.tile-0:hover {
                    background-color: #FAF8EF;
                    color: #FAF8EF;
                }
                </style>
                </head>
                <body>

                <script>
                function Player(){
                    this.role=null
                    this.uuid=null
                    this.round_json=null
                    this.action_block=false

                    this.btn_quick_start=document.getElementById("btn_quick_start")
                    this.btn_join=document.getElementById("btn_join")
                    this.btn_giveup=document.getElementById("btn_giveup")
                    this.slct_role=document.getElementById("slct_role")
                    this.slct_opponent=document.getElementById("slct_opponent")
                    this.btn_customize=document.getElementById("btn_customize")
                    this.txt_invite_url=document.getElementById("txt_invite_url")
                    
                    this.layout_control=function(obj=this){
                        if(!obj.is_game_in_progress()){
                            obj.btn_quick_start.disabled=false
                            obj.btn_join.disabled=false
                            obj.btn_giveup.disabled=true
                            obj.slct_role.disabled=false
                            obj.slct_opponent.disabled=false
                            obj.btn_customize.disabled=false
                            obj.txt_invite_url.disabled=true
                            document.styleSheets[1].disabled=true
                        }
                        else{
                            if(obj.role=="Attacker"&&obj.is_game_open_for_me()){
                                document.styleSheets[1].disabled=false
                            }
                            else{
                                document.styleSheets[1].disabled=true
                            }
                            obj.btn_quick_start.disabled=true
                            obj.btn_join.disabled=true
                            obj.btn_giveup.disabled=false
                            obj.slct_role.disabled=true
                            obj.slct_opponent.disabled=true
                            obj.btn_customize.disabled=true
                            if(obj.txt_invite_url.value!=""){
                                obj.txt_invite_url.disabled=false
                            }
                            else{
                                obj.txt_invite_url.disabled=true
                            }
                        }
                    }

                    this.is_game_in_progress=function(obj=this){
                        var flag_in_progress=false
                        if(obj.role!=null&&obj.uuid!=null&&obj.round_json!=null&&obj.round_json.round_score==-1){
                            flag_in_progress=true
                        }
                        return flag_in_progress
                    }

                    this.is_game_open_for_me=function(obj=this){
                        var flag_open_for_me=false
                        if(obj.is_game_in_progress()&&!obj.action_block){
                            switch(obj.role){
                                case "Attacker":
                                    flag_open_for_me=obj.round_json.attacker_wait&&obj.round_json.attacker_type=="Online"
                                    break
                                case "Defender":
                                    flag_open_for_me=obj.round_json.defender_wait&&obj.round_json.defender_type=="Online"
                                    break
                            }
                        }
                        return flag_open_for_me
                    }

                    this.get_invitation_url_for_pvp_game=function(obj=this){
                        var invitation_url=""
                        if(obj.is_game_in_progress()&&obj.round_json.attacker_type=="Online"&&obj.round_json.defender_type=="Online"){
                            var invite_role=""
                                switch(obj.role){
                                    case "Attacker":
                                        invite_role="Defender"
                                        break
                                    case "Defender":
                                        invite_role="Attacker"
                                        break
                                }
                                if(invite_role!=""){
                                    invitation_url=window.location.origin+"/?"+invite_role+"&"+obj.uuid
                                }
                        }
                        return invitation_url
                    }

                    this.show=function(message="\u00a0",obj=this){
                        var line1=document.getElementById("board-message").getElementsByTagName("div")[0]
                        var line2=document.getElementById("board-message").getElementsByTagName("div")[1]
                        if(message.startsWith("WAIT")&&line2.textContent.startsWith("WAIT")){
                            if(line2.textContent.length<35){
                                line2.textContent=line2.textContent+"."
                            }
                            else{
                                line2.textContent=message
                            }
                        }
                        else if(message!=line2.textContent){
                            line1.textContent=line2.textContent
                            line2.textContent=message
                        }
                    }

                    this.start=function(role="Defender",opponent="Random",obj=this){
                        var players_querystring=""
                        var opponent_role=""
                        switch(role){
                            case "Attacker":
                                players_querystring="attacker_type=Online&defender_type="+opponent
                                opponent_role="Defender"
                                break
                            case "Defender":
                                players_querystring="defender_type=Online&attacker_type="+opponent
                                opponent_role="Attacker"
                                break
                        }
                        if(opponent=="Online"&&opponent_role!=""){
                            players_querystring=players_querystring+"&unoccupied_role="+opponent_role
                        }
                        obj.role=role
                        obj.request("start=new&"+players_querystring,obj,obj.callback_start)
                    }

                    this.callback_start=function(obj,json){
                        obj.uuid=json.uuid
                        if(obj.role!=null&&obj.uuid!=null){
                            window.location=window.location.origin+"/?"+obj.role+"&"+obj.uuid
                        }
                    }

                    this.load=function(role,uuid,obj=this){
                        obj.role=role
                        obj.uuid=uuid
                        obj.render(obj)
                    }

                    this.render=function(obj=this){
                        if(obj.role!=null&&obj.uuid!=null&&!obj.action_block){
                            obj.action_block=true
                            obj.request("display&uuid="+obj.uuid,obj,obj.callback_render)
                        }
                    }

                    this.callback_render=function(obj,json){
                        obj.uuid=json.uuid
                        obj.round_json=json
                        if(obj.uuid!=null&&obj.round_json!=null){
                            var board_html=""
                            board_html=board_html+"<div>"
                            for(var row=0;row<obj.round_json.board_tiles.length;row++){
                                for(var col=0;col<obj.round_json.board_tiles[row].length;col++){
                                    board_html=board_html+"<div class='tile-"+obj.round_json.board_tiles[row][col]+"' data-type='board-tile' data-coordinate='"+row+","+col+"'>"+obj.round_json.board_tiles[row][col]+"</div>"
                                }
                            }
                            board_html=board_html+"</div>"
                            document.getElementById("board-container").innerHTML=board_html
                            if(obj.txt_invite_url.value!=obj.get_invitation_url_for_pvp_game()){
                                obj.txt_invite_url.value=obj.get_invitation_url_for_pvp_game()
                            }
                            obj.slct_role.value=obj.role
                            var opponent=""
                            switch(obj.role){
                                case "Attacker":
                                    opponent=obj.round_json.defender_type
                                    break
                                case "Defender":
                                    opponent=obj.round_json.attacker_type
                                    break
                            }
                            obj.slct_opponent.value=opponent
                        }
                        else{
                            obj.slct_role.value.value=""
                            obj.slct_opponent.value.value=""
                        }
                        obj.action_block=false
                        obj.layout_control(obj)
                        if(obj.is_game_open_for_me()){
                            obj.show("MY TURN NOW !")
                        }
                        else if(obj.is_game_in_progress()){
                            obj.show("WAIT for opponent's move.")
                        }
                        else if(obj.uuid!=null&&obj.round_json!=null&&("round_score" in obj.round_json)&&obj.round_json.round_score!=-1){
                            obj.show("GAME OVER, start or join a new game?")
                        }
                        else if(obj.uuid==null){
                            obj.round_json=null
                            obj.show("START or JOIN a new game?")
                        }
                    }

                    this.action=function(act,instruction,obj=this){
                        if(obj.is_game_open_for_me()){
                            switch(obj.role){
                                case "Attacker":
                                    if(act=="attack"){
                                        obj.show("I'm placing a new number.")
                                        obj.action_block=true
                                        obj.request("attack="+instruction+"&uuid="+obj.uuid,obj,obj.callback_action)
                                    }
                                    break
                                case "Defender":
                                    if(act=="defend"){
                                        switch(instruction){
                                            case "1,-1":
                                                obj.show("I'm moving... LEFTWARD")
                                                break
                                            case "0,-1":
                                                obj.show("I'm moving... UPWARD")
                                                break
                                            case "1,1":
                                                obj.show("I'm moving... RIGHTWARD")
                                                break
                                            case "0,1":
                                                obj.show("I'm moving... DOWNWARD")
                                                break
                                        }
                                        obj.action_block=true
                                        obj.request("defend="+instruction+"&uuid="+obj.uuid,obj,obj.callback_action)
                                    }
                                    break
                            }
                        }
                        else if(obj.is_game_in_progress()&&obj.round_json.attacker_type=="Online"&&obj.round_json.defender_type=="Online"&&instruction=="giveup"){
                            if(obj.round_json.attacker_wait){
                                obj.action_block=true
                                obj.request("attack=giveup&uuid="+obj.uuid,obj,obj.callback_action)
                            }
                            else if(obj.round_json.defender_wait){
                                obj.action_block=true
                                obj.request("defend=giveup&uuid="+obj.uuid,obj,obj.callback_action)
                            }
                        }
                    }

                    this.callback_action=function(obj,json){
                        obj.uuid=json.uuid
                        if(obj.uuid!=null){
                            setTimeout(function(){
                                obj.action_block=false
                                obj.render(obj)
                            },300)
                        }
                        else{
                            obj.round_json=null
                            obj.show("Time's up, game over.")
                            obj.layout_control()
                        }
                    }

                    this.join=function(obj=this){
                        obj.show("I'm joining a game...")
                        obj.request("get_an_unoccupied_game",obj,obj.callback_join)
                    }

                    this.callback_join=function(obj,json){
                        if(json["unoccupied"]!=null){
                            window.location=window.location.origin+"/?"+json["unoccupied"]["unoccupied_role"]+"&"+json["unoccupied"]["round_uuid"]
                        }
                        else{
                            obj.show("No game is available to join.")
                        }
                    }

                    this.request=function(command,obj,callback){
                        var xhttp=new XMLHttpRequest()
                        xhttp.open("GET","/?"+command,true)
                        xhttp.timeout=4000
                        xhttp.ontimeout=function(){
                            obj.request(command,obj,callback)
                            return
                        }
                        xhttp.onerror=function(){
                            obj.request(command,obj,callback)
                            return
                        }
                        xhttp.onreadystatechange=function(){
                            if (this.readyState==4&&this.status==200){
                                if (typeof(callback)!="undefined"){
                                    callback(obj,JSON.parse(xhttp.responseText))
                                }
                            }
                        }
                        xhttp.send()
                    }
                }

                window.addEventListener("load",function(event){
                    
                    document.styleSheets[1].disabled=true

                    var player=new Player()
                    var url=document.location.toString()
                    if(url.split("?").length==2&&url.split("?")[1].split("&").length==2){
                        var role=url.split("?")[1].split("&")[0]
                        var uuid=url.split("?")[1].split("&")[1]
                        player.show("Loading the game board......")
                        player.load(role,uuid,player)
                    }
                    else{
                        player.show("START or JOIN a new game?")
                        player.layout_control(player)
                    }
                    
                    setInterval(function(){
                        if(player.is_game_in_progress()&&!player.is_game_open_for_me()){
                            player.render(player)
                        }
                    },1000)

                    document.addEventListener("touchmove",function(event){event.preventDefault()},{passive:false})

                    player.btn_quick_start.addEventListener("click",function(event){
                        player.start()
                    })

                    player.btn_customize.addEventListener("click",function(event){
                        if(player.slct_role.value==""){player.slct_role.value="Defender"}
                        if(player.slct_opponent.value==""){player.slct_opponent.value="Random"}
                        player.start(player.slct_role.value,player.slct_opponent.value)
                    })

                    player.btn_join.addEventListener("click",function(event){
                        player.join()
                    })

                    player.btn_giveup.addEventListener("click",function(event){
                        player.show("I SURRENDER.")
                        switch(player.role){
                            case "Attacker":
                                player.action("attack","giveup")
                                break
                            case "Defender":
                                player.action("defend","giveup")
                                break
                        }
                    })

                    player.txt_invite_url.addEventListener("click",function(event){
                        event.target.select()
                    })

                    document.getElementById("board-container").addEventListener("click",function(event){
                        if(player.role=="Attacker"&&player.is_game_open_for_me()&&event.target.getAttribute("data-type")=="board-tile"&&event.target.className=="tile-0"){
                            player.action("attack",event.target.getAttribute("data-coordinate"))
                        }
                    })

                    document.addEventListener("keydown",function(event){
                        if(player.role=="Defender"){
                            switch(event.keyCode){
                                case 37:
                                    player.action("defend","1,-1")
                                    break
                                case 38:
                                    event.preventDefault()
                                    player.action("defend","0,-1")
                                    break
                                case 39:
                                    player.action("defend","1,1")
                                    break
                                case 40:
                                    event.preventDefault()
                                    player.action("defend","0,1")
                                    break
                            }
                        }
                    })

                    var xstart=null
                    var ystart=null
                    var xend=null
                    var yend=null
                    document.getElementById("board-container").addEventListener("touchstart",function(event){
                        if(player.role=="Defender"){
                            event.preventDefault()
                            xstart=event.changedTouches[0].clientX
                            ystart=event.changedTouches[0].clientY
                        }
                    })
                    document.getElementById("board-container").addEventListener("touchend",function(event){
                        if(player.role=="Defender"){
                            event.preventDefault()
                            xend=event.changedTouches[0].clientX
                            yend=event.changedTouches[0].clientY
                            xdiff=Math.abs(xend-xstart)
                            ydiff=Math.abs(yend-ystart)
                            var dim=null
                            var dir=null
                            if(Math.abs(xdiff-ydiff)>30&&xdiff>ydiff&&xdiff>50){
                                dim=1
                                dir=Math.sign(xend-xstart)
                            }
                            else if(Math.abs(xdiff-ydiff)>30&&xdiff<ydiff&&ydiff>50){
                                dim=0
                                dir=Math.sign(yend-ystart)
                            }
                            else{
                                return false
                            }
                            player.action("defend",dim+","+dir)
                        }
                    })
                })

                </script>
                <div id="board-control"><button id="btn_quick_start">QUICK START</button> <button id="btn_join">JOIN BATTLE</button> <button id="btn_giveup">GIVE UP</button></div>
                <div id="board-container"></div>
                <div id="board-message">
                    <div>&nbsp;</div>
                    <div>&nbsp;</div>
                </div>
                <div id="board-config">
                    I'm playing as <select id="slct_role">
                                        <option value="" selected>......</option>
                                        <option value="Attacker">Attacker</option>
                                        <option value="Defender">Defender</option>
                                   </select>
                    vs. <select id="slct_opponent">
                            <option value="" selected>......</option>
                            <option value="Random">random robot</option>
                            <option value="Strategy">strategic robot</option>
                            <option value="Online">human player</option>
                        </select>
                    <br/>
                    <button id="btn_customize">CUSTOMIZE A NEW GAME</button>
                    <br/>
                    Invitation URL <input type="text" id="txt_invite_url" readonly/> <a href="http://www.estyle.com.cn/" target="_blank">README</a>
                </div>
                </body>
                </html>
                """
                return [bytes(response_body,"utf-8")]
            ### the code below implements the logics of online gaming
            request_uuid=str(uuid4())
            Logger.log("DEBUG","Request received",\
                           "",\
                           {"request_uuid":request_uuid,\
                            "REMOTE_ADDR":environment["REMOTE_ADDR"],\
                            "QUERY_STRING":environment["QUERY_STRING"]\
                           }\
                      )
            status="200 OK"
            headers=[("Content-type","application/json")]
            response_header(status, headers)
            parameters={}
            parameters_list=environment["QUERY_STRING"].split("&")
            for parameter_pair in parameters_list:
                parameter=parameter_pair.split("=")
                parameters[parameter[0]]="" if len(parameter)!=2 else unquote(parameter[1])
            response_body={}
            if "start" in parameters and parameters["start"]=="new":
                if len(cls.ONLINE_ROUNDS)>=500:
                    response_body={}
                    response_body["uuid"]=None
                    response_body["message"]="Too many players, please wait and retry later"
                    Logger.log("INFO","Too many players to start a new game","",{"request_uuid":request_uuid})
                else:
                    round_uuid=str(uuid4())
                    cls.ONLINE_ROUNDS[round_uuid]={}
                    def online_round():
                        arg_attacker_type=parameters.get("attacker_type","Random")
                        arg_defender_type=parameters.get("defender_type","Online")
                        if arg_attacker_type=="Manual": arg_attacker_type="Random"
                        if arg_defender_type=="Manual": arg_defender_type="Online"
                        if arg_attacker_type!="Online" and arg_defender_type!="Online": arg_defender_type="Online"
                        cls.ONLINE_ROUNDS[round_uuid]["round"]=Round(uuid=round_uuid,\
                                        board_shape=parameters.get("board_shape","[4,4]"),\
                                        board_tiles=parameters.get("board_tiles","[]"),\
                                        attacker_type=arg_attacker_type,\
                                        defender_type=arg_defender_type\
                                        )
                        cls.ONLINE_ROUNDS[round_uuid]["board_tiles"]=[]
                        cls.ONLINE_ROUNDS[round_uuid]["attacker_type"]=arg_attacker_type
                        cls.ONLINE_ROUNDS[round_uuid]["attacker_wait"]=False
                        cls.ONLINE_ROUNDS[round_uuid]["attacker_instruction"]={}
                        cls.ONLINE_ROUNDS[round_uuid]["defender_type"]=arg_defender_type
                        cls.ONLINE_ROUNDS[round_uuid]["defender_wait"]=False
                        cls.ONLINE_ROUNDS[round_uuid]["defender_instruction"]={}
                        cls.ONLINE_ROUNDS[round_uuid]["last_visit"]=datetime.now()
                        cls.ONLINE_ROUNDS[round_uuid]["last_update"]=datetime.now()
                        cls.ONLINE_ROUNDS[round_uuid]["unoccupied_role"]=""
                        if arg_attacker_type=="Online" and arg_defender_type=="Online" and parameters.get("unoccupied_role","") in ("Attacker","Defender"):
                            cls.ONLINE_ROUNDS[round_uuid]["unoccupied_role"]=parameters["unoccupied_role"]
                        cls.ONLINE_ROUNDS[round_uuid]["round_score"]=cls.ONLINE_ROUNDS[round_uuid]["round"].start()
                    try:
                        cls.ONLINE_ROUNDS[round_uuid]["thread"]=threading.Thread(target=online_round)
                        cls.ONLINE_ROUNDS[round_uuid]["thread"].setDaemon(True)
                        cls.ONLINE_ROUNDS[round_uuid]["thread"].start()
                        response_body={}
                        response_body["uuid"]=round_uuid
                        response_body["message"]="A new game might have started"
                    except Exception as err:
                        Logger.log("ERROR","Request to start a new game failed",\
                                       "",\
                                       {"request_uuid":request_uuid,\
                                        "ERROR_MESSAGE":str(err)\
                                       }\
                                  )
                        response_body={}
                        response_body["uuid"]=None
                        response_body["message"]="Failed to start a new online game"
            elif "get_an_unoccupied_game" in parameters:
                response_body={}
                response_body["uuid"]=None
                response_body["message"]="List of unoccupied games"
                response_body["unoccupied"]=None
                all_unoccupied=[]
                for round_uuid in cls.ONLINE_ROUNDS:
                    if cls.ONLINE_ROUNDS[round_uuid]["unoccupied_role"]!=""\
                        and (datetime.now()-cls.ONLINE_ROUNDS[round_uuid]["last_visit"]).seconds<2:
                            all_unoccupied.append(\
                                {"round_uuid":round_uuid,\
                                 "unoccupied_role":cls.ONLINE_ROUNDS[round_uuid]["unoccupied_role"]\
                                }\
                            )
                if len(all_unoccupied)>0:
                    response_body["unoccupied"]=random.choice(all_unoccupied)
            elif "uuid" in parameters and parameters["uuid"] in cls.ONLINE_ROUNDS:
                if "display" in parameters:
                    cls.ONLINE_ROUNDS[parameters["uuid"]]["last_visit"]=datetime.now()
                    response_body={}
                    response_body["uuid"]=parameters["uuid"]
                    response_body["message"]="Current situation"
                    response_body["board_tiles"]=deepcopy(cls.ONLINE_ROUNDS[parameters["uuid"]]["board_tiles"])
                    response_body["attacker_type"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_type"]
                    response_body["attacker_wait"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_wait"]
                    response_body["defender_type"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_type"]
                    response_body["defender_wait"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_wait"]
                    response_body["unoccupied_role"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["unoccupied_role"]
                    response_body["last_visit"]=str(cls.ONLINE_ROUNDS[parameters["uuid"]]["last_visit"])
                    response_body["last_update"]=str(cls.ONLINE_ROUNDS[parameters["uuid"]]["last_update"])
                    response_body["round_score"]=cls.ONLINE_ROUNDS[parameters["uuid"]].get("round_score",-1)
                elif "attack" in parameters:
                    response_body={}
                    response_body["uuid"]=parameters["uuid"]
                    if cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_wait"]:
                        cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_instruction"]={"keepgoing":True,"location":None}
                        if parameters["attack"]!="giveup":
                            cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_instruction"]["location"]=[]
                            for dim in parameters["attack"].split(","):
                                cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_instruction"]["location"].append(-1 if not dim.isnumeric() else int(dim))
                            response_body["message"]="Attack instruction is sent"
                            response_body["attacker_instruction"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_instruction"]
                        else:
                            cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_instruction"]["keepgoing"]=False
                            response_body["message"]="Attacker surrendered"
                        cls.ONLINE_ROUNDS[parameters["uuid"]]["attacker_wait"]=False
                    else:
                        response_body["message"]="Attack is not possible now"
                elif "defend" in parameters:
                    response_body={}
                    response_body["uuid"]=parameters["uuid"]
                    if cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_wait"]:
                        cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_instruction"]={"keepgoing":True,"dimension":None,"direction":None}
                        if parameters["defend"]!="giveup":
                            dim_and_dir=parameters["defend"].split(",")
                            if len(dim_and_dir)==2:
                                cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_instruction"]["dimension"]=-1 if not dim_and_dir[0].isnumeric() else int(dim_and_dir[0])
                                cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_instruction"]["direction"]=0 if dim_and_dir[1] not in ("-1","1") else int(dim_and_dir[1])
                            response_body["message"]="Defend instruction is sent"
                            response_body["defender_instruction"]=cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_instruction"]
                        else:
                            cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_instruction"]["keepgoing"]=False
                            response_body["message"]="Defender surrendered"
                        cls.ONLINE_ROUNDS[parameters["uuid"]]["defender_wait"]=False
                    else:
                        response_body["message"]="Defend is not possible now"
                else:
                    response_body={}
                    response_body["uuid"]=None
                    response_body["message"]="Nothing happended"
            else:
                response_body={}
                response_body["uuid"]=None
                response_body["message"]="Nothing happended"
            Logger.log("DEBUG","Message responded",\
                           "",\
                           {"request_uuid":request_uuid,\
                            "response_body":response_body\
                           }\
                      )
            return [bytes(json.dumps(response_body),"utf-8")]
        cls.__is_stopped=False
        with wsgi.make_server("",80,server_process,handler_class=cls.__class_for_hiding_console_log_only) as httpd:
            httpd.serve_forever()
        ### because of the WITH statement above
        ### the two statements below won't run unless httpd.serve_forever() is interrupted
        Logger.log("CRITICAL","Server is down",{"ERROR_MESSAGE":str(err)})
        cls.__is_stopped=True

    @classmethod
    def __clean_online_rounds(cls):
        while True:
            sleep(10)
            rounds_to_be_deleted=[]
            rounds_to_be_ended=[]
            for round_uuid in cls.ONLINE_ROUNDS:
                if not cls.ONLINE_ROUNDS[round_uuid]["thread"].is_alive() and (datetime.now()-cls.ONLINE_ROUNDS[round_uuid]["last_visit"]).seconds>30 and (datetime.now()-cls.ONLINE_ROUNDS[round_uuid]["last_update"]).seconds>30:
                    rounds_to_be_deleted.append(round_uuid)
                elif (datetime.now()-cls.ONLINE_ROUNDS[round_uuid]["last_visit"]).seconds>300 and (datetime.now()-cls.ONLINE_ROUNDS[round_uuid]["last_update"]).seconds>300:
                    cls.ONLINE_ROUNDS[round_uuid]["attacker_instruction"]={"keepgoing":False,"location":None}
                    cls.ONLINE_ROUNDS[round_uuid]["attacker_wait"]=False
                    cls.ONLINE_ROUNDS[round_uuid]["defender_instruction"]={"keepgoing":False,"dimension":None,"direction":None}
                    cls.ONLINE_ROUNDS[round_uuid]["defender_wait"]=False
                    rounds_to_be_ended.append(round_uuid)
            if len(rounds_to_be_ended)>0:
                Logger.log("DEBUG","Ended pending rounds","",{"pending_rounds":rounds_to_be_ended})
            for round_uuid in rounds_to_be_deleted:
                del cls.ONLINE_ROUNDS[round_uuid]["round"]
                del cls.ONLINE_ROUNDS[round_uuid]
            if len(rounds_to_be_deleted)>0:
                Logger.log("DEBUG","Cleaned dead rounds","",{"dead_rounds":rounds_to_be_deleted})

    @classmethod
    def serve_forever(cls):
        gc_thread=threading.Thread(target=cls.__clean_online_rounds)
        gc_thread.setDaemon(True)
        gc_thread.start()
        restart_count=0
        while True:
            if cls.__is_stopped:
                server_thread=threading.Thread(target=cls.__server_daemon)
                server_thread.setDaemon(True)
                server_thread.start()
                restart_count=restart_count+1
                if restart_count>10:
                    sys.exit("Server restarts too many times")
            sleep(10)


class Logger():
    """
    logger is implemented with queue and file.write()

    key properties:
        __LOGQUEUE          queue, store JSON message with this structure:
                                    "log_datetime":str_datetime_now,
                                    "log_level":str_CRITICAL_to_DEBUG,
                                    "log_message":str_message,
                                    "log_round_uuid":str_uuid,
                                    "log_details":{k:w,*}
                                    log_details dictionary does not have uniform definition

    key methods:
        log()               None, put a message into __LOGQUEUE
        __persist()         None, get a message from __LOGQUEUE and write it into log file with infinite loop
        start()             None, call __persist() in a child thread
        wait_till_finish()  None, call queue.join() to block main thread, write last log before sys.exit()

    remarks:
        logger class is not allowed to initialize an instance.
    """
    __LOGQUEUE=queue.Queue()

    def __init__(self):
        raise Exception("Logger class is not allowed to initialize")

    @classmethod
    def log(cls,log_level,log_message,log_round_uuid="",log_details={}):
        try:
            message=json.dumps({"log_datetime":str(datetime.now()),\
                                "log_level":log_level,\
                                "log_message":log_message,\
                                "log_round_uuid":log_round_uuid,\
                                "log_details":log_details})
        except Exception as err:
            message=json.dumps({"log_datetime":str(datetime.now()),\
                                 "log_level":"CRITICAL",\
                                 "log_message":"Error occurs while logging",\
                                 "log_round_uuid":log_round_uuid,\
                                 "log_details":{"ERROR_MESSAGE":str(err)}})
        cls.__LOGQUEUE.put(message)

    @classmethod
    def __persist(cls,*,excluded_levels=[]):
        if not os.path.exists(sys.path[0]+"/logs/"):
                os.mkdir(sys.path[0]+"/logs/")
        while True:
            log_line=cls.__LOGQUEUE.get()
            log_file_name=sys.path[0]+"/logs/"+datetime.now().strftime("%Y-%m-%d")+".log"
            if json.loads(log_line)["log_level"] not in excluded_levels:
                with open(log_file_name,"a") as log_file:
                    log_file.write(log_line)
                    log_file.write("\n")
            cls.__LOGQUEUE.task_done()

    @classmethod
    def start(cls,*,excluded_levels=[]):
        logger_thread=threading.Thread(target=cls.__persist,kwargs={"excluded_levels":excluded_levels})
        logger_thread.setDaemon(True)
        logger_thread.start()

    @classmethod
    def wait_till_finish(cls):
        cls.__LOGQUEUE.join()


def main():
    args={}
    for index in range(1,len(sys.argv)):
        arg=(sys.argv[index].lstrip("-")).split("=")
        args[arg[0]]="" if len(arg)!=2 else arg[1]
    Logger.start(excluded_levels=["DEBUG"] if "localonly" in args and args["localonly"]=="auto" else [])
    if "localonly" in args:
        while True:
            try:
                arg_board_shape=args.get("board_shape","[4,4]")
                input_board_shape="" if args["localonly"]=="auto" else input("Specify board_shape (default is "+arg_board_shape+"): ").strip()
                if input_board_shape=="": input_board_shape=arg_board_shape

                arg_board_tiles=args.get("board_tiles","[]")
                input_board_tiles="" if args["localonly"]=="auto" else input("Specify board_tiles (default is "+arg_board_tiles+", [] presents normal board): ").strip()
                if input_board_tiles=="": input_board_tiles=arg_board_tiles

                arg_attacker_type=args.get("attacker_type","Random")
                input_attacker_type="" if args["localonly"]=="auto" else input("Specify attacker_type (default is "+arg_attacker_type+"): ").strip()
                if input_attacker_type=="": input_attacker_type=arg_attacker_type
                if input_attacker_type=="Online":
                    print("Online attacker is disabled, switch to Random attacker")
                    input_attacker_type="Random"
                if args["localonly"]=="auto" and input_attacker_type=="Manual":
                    input_attacker_type="Random"

                arg_defender_type=args.get("defender_type","Manual")
                input_defender_type="" if args["localonly"]=="auto" else input("Specify defender_type (default is "+arg_defender_type+"): ").strip()
                if input_defender_type=="": input_defender_type=arg_defender_type
                if input_defender_type=="Online":
                    print("Online defender is disabled, switch to Manual defender")
                    input_defender_type="Manual"
                if  args["localonly"]=="auto" and input_defender_type=="Manual":
                    input_defender_type="Random"

                round=Round(board_shape=input_board_shape,\
                            board_tiles=input_board_tiles,\
                            attacker_type=input_attacker_type,\
                            defender_type=input_defender_type)
                round.start()
            except (SystemExit,KeyboardInterrupt):
                Logger.log("WARNING","Localonly round is interrupted, quit by force")
                Logger.wait_till_finish()
                sys.exit()
            except Exception as err:
                Logger.log("ERROR","Localonly round has something wrong",\
                               "",\
                               {"ERROR_MESSAGE":str(err)}\
                          )
    else:
        try:
            Server.serve_forever()
        except (SystemExit,KeyboardInterrupt):
            Logger.log("WARNING","Server is interrupted, quit by force")
            Logger.wait_till_finish()
            sys.exit()
        except Exception as err:
            Logger.log("ERROR","Server has something wrong",\
                           "",\
                           {"ERROR_MESSAGE":str(err)}\
                      )

if __name__=="__main__":
    main()
