main.py - import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

def fetch_user_data(username):
    url = f"https://api.warpcast.com/v2/user-by-username?username={username}"
    response = requests.get(url)
    response.raise_for_status()
    user_data = response.json()
    fid = user_data['result']['user']['fid']
    return fid

def fetch_user_connections(username):
    try:
        fid = fetch_user_data(username)
        url = f"https://api.warpcast.com/v2/followers?fid={fid}"
        connections = []
        cursor = None

        while True:
            params = {'limit': 100}
            if cursor:
                params['cursor'] = cursor

            response = requests.get(url, params=params)
            response.raise_for_status()
            result = response.json()

            # Debug: Print the structure of the result
            print(f"API Response for {username}:")
            print(json.dumps(result, indent=2))

            # Check the structure of the response
            if 'result' not in result:
                print(f"'result' key not found in response for user {username}")
                print("Response keys:", result.keys())
                raise KeyError(f"'result' key not found in response for user {username}")

            if 'users' not in result['result']:
                print(f"'users' key not found in result for user {username}")
                print("Result keys:", result['result'].keys())
                raise KeyError(f"'users' key not found in result for user {username}")

            users = result['result']['users']
            if not isinstance(users, list):
                print(f"'users' is not a list for user {username}")
                print(f"Type of 'users': {type(users)}")
                raise TypeError(f"'users' is not a list for user {username}")

            connections.extend([(user.get('username', 'Unknown'),
                                 user.get('timestamp', 'Unknown'))
                                for user in users])

            cursor = result.get('next', {}).get('cursor')
            if not cursor:
                break

        return connections
    except requests.exceptions.RequestException as e:
        print(f"HTTP Error for user {username}: {e}")
        return []
    except KeyError as e:
        print(f"Data structure error for user {username}: {e}")
        return []
    except TypeError as e:
        print(f"Data type error for user {username}: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error for user {username}: {e}")
        return []

def fetch_data(usernames):
    data = {}
    for username in usernames:
        try:
            connections = fetch_user_connections(username)
            data[username] = {'connections': connections}
        except Exception as e:
            print(f"Error fetching data for user {username}: {e}")
            data[username] = {'connections': [], 'error': str(e)}
    return data

def create_graph(data, timestamp):
    G = nx.Graph()
    farcaster_epoch = pd.Timestamp('2021-01-01 00:00:00', tz='UTC')
    timestamp_seconds = (pd.to_datetime(timestamp, utc=True) - farcaster_epoch).total_seconds()

    for user, info in data.items():
        if 'error' in info:
            continue
        G.add_node(user)
        for connection, time in info['connections']:
            if time == 'Unknown':
                print(f"Skipping connection '{connection}' of user '{user}' due to unknown timestamp.")
                continue
            try:
                time_seconds = int(time)
                if time_seconds <= timestamp_seconds:
                    G.add_edge(user, connection)
            except ValueError:
                print(f"Invalid timestamp '{time}' for connection '{connection}' of user '{user}'")
    return G

def calculate_metrics(G):
    num_edges = G.number_of_edges()
    adj_matrix = nx.adjacency_matrix(G).todense()
    shortest_paths = dict(nx.all_pairs_shortest_path_length(G))
    return num_edges, adj_matrix, shortest_paths

def create_plotly_traces(G, pos):
    edge_trace = go.Scatter(x=[],
                            y=[],
                            line=dict(width=0.5, color='#888'),
                            hoverinfo='none',
                            mode='lines')

    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_trace['x'] += tuple([x0, x1, None])
        edge_trace['y'] += tuple([y0, y1, None])

    node_trace = go.Scatter(x=[],
                            y=[],
                            text=[],
                            mode='markers+text',
                            hoverinfo='text',
                            marker=dict(showscale=True,
                                        colorscale='YlGnBu',
                                        size=10))

    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += tuple([x])
        node_trace['y'] += tuple([y])
        node_trace['text'] += tuple([node])

    return edge_trace, node_trace

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/visualize', methods=['POST'])
def visualize():
    try:
        usernames = request.json['usernames']
        timestamp = request.json['timestamp']

        # Validate the timestamp format
        try:
            pd.to_datetime(timestamp)
        except ValueError:
            return jsonify({'error': 'Invalid timestamp format.'}), 400

        data = fetch_data(usernames)
        G = create_graph(data, timestamp)

        if G.number_of_nodes() == 0:
            return jsonify({'error': 'Graph has no nodes or edges.'}), 400

        num_edges, adj_matrix, shortest_paths = calculate_metrics(G)

        pos = nx.spring_layout(G)
        edge_trace, node_trace = create_plotly_traces(G, pos)

        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title='<b>Cloud Cartography: Social Network Visualization</b>',
                titlefont_size=20,
                showlegend=False,
                hovermode='closest',
                margin=dict(b=20, l=20, r=20, t=50),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)))

        return jsonify({
            'fig': fig.to_dict(),
            'num_edges': num_edges,
            'adj_matrix': adj_matrix.tolist(),
            'shortest_paths': shortest_paths,
            'errors': {
                username: info['error']
                for username, info in data.items() if 'error' in info
            }
        })
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({'error': 'An unexpected error occurred.'}), 500

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        print(f"Error starting Flask application: {e}")