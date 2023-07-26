from constants import *
from piece import Piece
from redtangle_local import *
from proto import redtangle_pb2_grpc, redtangle_pb2
import grpc
import pyautogui
import traceback
import json
import argparse
from time import sleep

class RedtangleServerError(Exception):
    def __init__(self):
        pass
class GameFullError(Exception):
    def __init__(self):
        pass

class RedTangleClient:
    def __init__(self, host='localhost', server_port=50051):
        print(host)
        self._host = host
        self._server_port = server_port
        #self._channel = grpc.insecure_channel('localhost:50051', options=(('grpc.enable_http_proxy', 0),))
        #print(self._channel)
        self._board = [[Piece(None, [None, None, None, None]) for i in range(GRID_SIZE)] for j in range(GRID_SIZE)]
        self._turn = ''
        self._winner = ''
        self._team_color = ''
        self._opponent = ''
        self._connected = False
        args = self.parseCommandLine()
        self.setup_client(
            args.host,
            args.port,
            args.api_key,
            args.auth_token,
            args.timeout,
            args.use_tls,
            args.servername,
            args.ca_path,
        )
        self._run()

    def parseCommandLine(self):
        parser = argparse.ArgumentParser(
            description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
        )
        parser.add_argument("--host", default="192.168.1.93", help="The host to connect to")
        parser.add_argument("--port", type=int, default=50051, help="The port to connect to")
        parser.add_argument(
            "--timeout", type=int, default=10, help="The call timeout, in seconds"
        )
        parser.add_argument(
            "--api_key", default=None, help="The API key to use for the call"
        )
        parser.add_argument(
            "--servername",
            type=str,
            default="",
            help="The servername to use to call the API.",
        )
        parser.add_argument(
            "--ca_path", type=str, default="grpc.crt", help="The path to the CA."
        )
        parser.add_argument(
            "--auth_token", default=None, help="The JWT auth token to use for the call"
        )
        parser.add_argument(
            "--use_tls",
            type=bool,
            default=False,
            help="Enable when the server requires TLS",
        )
        args = parser.parse_args()
        return args

    def setup_client(self, host, port, api_key, auth_token, timeout, use_tls, servername_override, ca_path):
        print(f"{host}:{port}")
        if use_tls:
            with open(ca_path, "rb") as f:
                creds = grpc.ssl_channel_credentials(f.read())
            channel_opts = ()
            if servername_override:
                channel_opts += (
                    (
                        "grpc.ssl_target_name_override",
                        servername_override,
                    ),
                )
            self._channel = grpc.secure_channel(f"{host}:{port}", creds, channel_opts)
        else:
            self._channel = grpc.insecure_channel(f"{host}:{port}", options=(("grpc.enable_http_proxy", 0),))
        
        self._client = redtangle_pb2_grpc.RedTangleStub(self._channel)

    
    def init_game(self):
        pygame.init()
        self.window = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()

    def _check_codes(self, server_status):
        if server_status == redtangle_pb2.SERVER_ERROR:
                raise RedtangleServerError()
            
        elif server_status == redtangle_pb2.GAME_FULL:
                raise GameFullError()

    def __str_to_color(self, str):
        match str:
            case 'White':
                return WHITE
            case 'Black':
                return BLACK
            case '':
                return None

    def decode_board(self, board_json):
        my_dict = json.loads(board_json)
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                team_color = my_dict[str((row, col))]['team_color']
                orientation = my_dict[str((row, col))]['orientation']
                self._board[row][col] = Piece(color=self.__str_to_color(team_color),
                                              orien=[self.__str_to_color(ori) for ori in orientation])

    def _update_game_status(self, game_status):
        if self._opponent and self._opponent != game_status.opponent:
            self.user_left()
        self._turn = game_status.turn
        self._winner = game_status.winner
        self._opponent = game_status.opponent
        self.decode_board(game_status.board)

    def set_status(self, status):
        self._check_codes(server_status=status.server_status)
        self._update_game_status(game_status=status.game_status)
        
    def connect(self):
        name = pyautogui.prompt(title='Redtangle', text='Enter username:')
        while not name:
            if name == None:
                raise UserQuit()
            name = pyautogui.prompt(title='Redtangle', text='Not a valid username. Enter a different username:')
        
        self._username = redtangle_pb2.Username(username=name)
        connection_response = self._client.Connect(self._username)
        self._check_codes(connection_response.status.server_status)
        while connection_response.status.server_status == redtangle_pb2.USER_EXISTS:
            print('User already exists.')
            self._username = redtangle_pb2.Username(username=pyautogui.prompt(title='Redtangle', text='Username already exists. Enter a different username:'))
            connection_response = self._client.Connect(self._username)
            self._check_codes(connection_response.status.server_status)
        self._connected = True
        self._team_color = connection_response.team_color
        self._update_game_status(connection_response.status.game_status)
            
    
    def _update_board(self):
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                pygame.draw.rect(self.window, BLACK, 
                                pygame.Rect(col * SQUARE_WIDTH, 
                                row * SQUARE_HEIGHT,
                                SQUARE_WIDTH, SQUARE_HEIGHT))
                pygame.draw.rect(self.window, RedTangleLocal.get_square_color(row, col), 
                                pygame.Rect(col * SQUARE_WIDTH + EDGE_SIZE, 
                                row * SQUARE_HEIGHT + EDGE_SIZE,
                                SQUARE_WIDTH - EDGE_SIZE, SQUARE_HEIGHT - EDGE_SIZE))
                if self._board[row][col].get_team() != None:
                   self._board[row][col].draw(self.window, row, col)
        pygame.display.update()

    # Take events from keyboard and make requests to server
    def _process_actions(self):
        status_updated = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise UserQuit()
            elif event.type == pygame.MOUSEBUTTONDOWN and not self._winner:
                if event.button == LEFT_CLICK:
                    print('Left Click Detected')
                    yy, xx = pygame.mouse.get_pos()
                    response = self._client.Select(redtangle_pb2.SelectRequest(username=self._username,
                                                                    position=redtangle_pb2.Position(x=xx, y=yy)))
                    self.set_status(response)
                    status_updated = True
                elif event.button == RIGHT_CLICK:
                    print('Right Click Detected')
                    response = self._client.EndTurn(self._username)
                    self.set_status(response)
                    status_updated = True
                elif event.button == SCROLL_UP:
                    print('Scroll Up')
                    response = self._client.Rotate(redtangle_pb2.RotateRequest(username=self._username, 
                                                                    clockwise_rotation=True))
                    self.set_status(response)
                    status_updated = True
                elif event.button == SCROLL_DOWN:
                    print('Scroll Down')
                    response = self._client.Rotate(redtangle_pb2.RotateRequest(username=self._username, 
                                                                    clockwise_rotation=False))
                    self.set_status(response)
                    status_updated = True
        if not status_updated:
            response_status = self._client.GetStatus(self._username)
            self.set_status(response_status)
        return True
    
    # While waiting for an opponent, check if client has requested to quit the game
    def user_quit(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise UserQuit()

    
    def user_left(self):
        response = pyautogui.confirm(title='Redtangle',
                                     text=f'{self._opponent} has left the game.', 
                                     buttons=['OK', 'Leave Game']
                                    )
        if response == 'Leave Game':
            raise UserQuit()

    def close(self):
        if self._connected:
            self._client.Disconnect(self._username)
            self._connected = False
        self._channel.close()

    # Main Loop   
    def _run(self):
        try:
            self.connect()
            self.init_game()
            caption = ''
            while True:
                if self._winner:
                    caption = f'{TITLE}: {self._username.username if self._winner == self._team_color else self._opponent} Won'
                    self.user_quit()
                elif self._opponent:
                    caption = f'{TITLE}: {self._username.username + " vs " + self._opponent} - '
                    caption += "Your Turn" if self._team_color == self._turn else self._opponent + "'s Turn"
                    self._process_actions()
                else:
                    caption = f'{TITLE}: Waiting for an opponent to join...'
                    response_status = self._client.GetStatus(self._username)
                    self.set_status(response_status)
                    self.user_quit()
                
                pygame.display.set_caption(caption)
                self.clock.tick(FPS)
                self._update_board()
    
        except UserQuit as uq:
            print('User Quit')
        
        except Exception as e:
            pyautogui.alert(title='Redtangle',
                            text=f'Error:{traceback.format_exc()}')
            print(f'{traceback.format_exc()}')
        
        finally:
            self.close()

# Runs the Client
if __name__ == "__main__":
       RedTangleClient()