import jsonlines

from api.directory_api import DirectoryAPI
from graph_structure.edge import Edge, ParentEdge, RoleEdge
from graph_structure.node import Node, IdentityNode, ResourceNode, \
    generate_resource_id, generate_resource_asset_type, generate_identity_id_type


class Graph:
    def __init__(self):
        self.edges = []
        self.nodes = {}
        self.root_resource = {}
        google_directory_api = DirectoryAPI()
        self.groups_dictionary = google_directory_api.fetch_users_in_groups()

    def __get_groups_of_user(self, p_user_email):
        lst_groups_user_belong_to = []
        for group in self.groups_dictionary:
            if p_user_email in self.groups_dictionary[group]:
                lst_groups_user_belong_to.append(group)
        return lst_groups_user_belong_to

    def __get_resources_by_identity(self, p_identity_id: str):
        return [edge for edge in self.edges if
                type(edge) == RoleEdge and edge.from_node.id == p_identity_id]

    def __get_resources_by_parent_resource(self, p_parent_resource_id: str):
        return [edge.to_node for edge in self.edges if
                type(edge) == ParentEdge and edge.from_node.id == p_parent_resource_id]

    def __get_parent_by_resource(self, p_node_id: str):
        return [edge.from_node.id for edge in self.edges if
                type(edge) == ParentEdge and edge.to_node.id == p_node_id][0]

    def __get_identities_by_resource(self, p_resource_id: str):
        return [edge for edge in self.edges if
                type(edge) == RoleEdge and edge.to_node.id == p_resource_id]

    def __create_identities_relationships(self, p_curr_resource_node, lst_bindings):
        for binding in lst_bindings:
            role = binding["role"]
            lst_identities = binding["members"]

            for identity_str in lst_identities:
                identity_id, identity_type = generate_identity_id_type(identity_str)
                identity_node = IdentityNode(identity_id, identity_type)
                self.add_node(identity_node)
                role_edge = RoleEdge(identity_node, p_curr_resource_node, role)
                self.add_edge(role_edge)

    def __create_ancestors_relationships(self, p_curr_resource_node, p_lst_ancestors):
        child_node = p_curr_resource_node
        for i in range(1, len(p_lst_ancestors)):
            ancestor_id = p_lst_ancestors[i]
            ancestor_node = ResourceNode(ancestor_id)
            self.add_node(ancestor_node)
            parent_edge = ParentEdge(ancestor_node, child_node)
            self.add_edge(parent_edge)
            child_node = ancestor_node

    def __create_resource_node(self, p_node_id, p_asset_type):
        curr_resource_node = ResourceNode(p_node_id, p_asset_type)
        self.add_node(curr_resource_node)
        return curr_resource_node

    def __get_recursive_hierarchy(self, p_resource_id: str, p_path: list):
        if self.root_resource.id == p_resource_id:
            return p_path
        parent_resource = self.__get_parent_by_resource(p_resource_id)
        p_path.append(parent_resource)
        return self.__get_recursive_hierarchy(parent_resource, p_path)

    def __get_children_resources_bfs(self, p_root_resource: ResourceNode):
        explored = []
        queue = [p_root_resource]
        while queue:
            node = queue.pop(0)
            if node not in explored:
                explored.append(node)
                neighbours = self.__get_resources_by_parent_resource(node.id)
                for neighbour in neighbours:
                    queue.append(neighbour)
        return explored

    def __update_edged_with_node(self, p_node: Node):
        for i, edge in enumerate(self.edges):
            if edge.from_node.id == p_node.id:
                self.edges[i].from_node = p_node
            elif edge.to_node.id == p_node.id:
                self.edges[i].to_node = p_node

    def __get_direct_resources_of_identity(self, p_identity_id):
        lst_resources_connected = self.__get_resources_by_identity(p_identity_id)
        is_user_identity = self.nodes.get(p_identity_id).type == "user"
        if is_user_identity:
            lst_groups_user_belong_to = self.__get_groups_of_user(p_identity_id)
            for group_identity in lst_groups_user_belong_to:
                lst_resources_connected += self.__get_resources_by_identity(group_identity)
        return lst_resources_connected

    def create_graph(self):
        with jsonlines.open('./data/data_file.json') as reader:
            for line in reader:
                node_id = generate_resource_id(line["name"])
                asset_type = generate_resource_asset_type(line["asset_type"])
                curr_resource_node = self.__create_resource_node(node_id, asset_type)

                if curr_resource_node.asset_type != "Organization":
                    lst_ancestors = line["ancestors"]
                    self.__create_ancestors_relationships(curr_resource_node, lst_ancestors)

                lst_bindings = line["iam_policy"]["bindings"]
                self.__create_identities_relationships(curr_resource_node, lst_bindings)

    def add_node(self, p_node: Node):
        node_in_graph = self.nodes.get(p_node.id)
        if node_in_graph is not None:
            is_need_to_update_asset_type = type(node_in_graph) == ResourceNode and \
                                           type(p_node) == ResourceNode and \
                                           p_node.asset_type != "" and \
                                           node_in_graph.asset_type != p_node.asset_type
            if is_need_to_update_asset_type:
                self.nodes[p_node.id] = p_node
                self.__update_edged_with_node(p_node)
        else:
            self.nodes[p_node.id] = p_node

        if (type(p_node) == ResourceNode) and (p_node.asset_type == "Organization"):
            self.root_resource = p_node

        return p_node

    def add_edge(self, p_edge: Edge):
        is_exist = next((edge for edge in self.edges if
                         edge.from_node.id == p_edge.from_node.id and
                         edge.to_node.id == p_edge.to_node.id and
                         edge.type == p_edge.type), None)
        if is_exist is None:
            self.edges.append(p_edge)

    def print_relationships(self):
        for edge in self.edges:
            print(edge.from_node.id + "---" + edge.type + "--->" + edge.to_node.id)

    def get_resource_hierarchy(self, p_resource_id: str):
        if self.root_resource.id == p_resource_id:
            return "That was easy! You are searching the root organization"
        path = []
        return self.__get_recursive_hierarchy(p_resource_id, path)

    def get_user_permissions(self, p_identity_id: str):
        lst_permissions = list()
        lst_resources_connected = self.__get_direct_resources_of_identity(p_identity_id)

        for edge in lst_resources_connected:
            role = edge.type
            resource_node = edge.to_node
            lst_children_resources = self.__get_children_resources_bfs(resource_node)
            for node in lst_children_resources:
                permission_tuple = (node.id, node.asset_type, role)
                if permission_tuple not in lst_permissions:
                    lst_permissions.append(permission_tuple)

        return lst_permissions

    def get_resources_permitted(self, p_resource_id: str):
        lst_permitted_identities = []
        lst_parent_resources = self.get_resource_hierarchy(p_resource_id)
        lst_parent_resources.append(p_resource_id)

        for resource_id in lst_parent_resources:
            for edge in self.__get_identities_by_resource(resource_id):
                identity_node = edge.from_node
                if identity_node.type == "group":
                    for user_id in self.groups_dictionary[identity_node.id]:
                        identity_tuple = (user_id, edge.type)
                        if identity_tuple not in lst_permitted_identities:
                            lst_permitted_identities.append(identity_tuple)
                identity_tuple = (identity_node.id, edge.type)
                if identity_tuple not in lst_permitted_identities:
                    lst_permitted_identities.append(identity_tuple)

        return lst_permitted_identities
