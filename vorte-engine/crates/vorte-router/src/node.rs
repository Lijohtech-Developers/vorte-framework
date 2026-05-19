use std::fmt;

use vorte_http::Method;

use crate::params::Params;

pub const METHOD_COUNT: usize = 9;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum NodeType {
    Static,
    Param,
    Wildcard,
}

#[derive(Clone)]
pub struct Handlers {
    entries: [Option<u32>; METHOD_COUNT],
}

impl Handlers {
    pub fn new() -> Self {
        Self {
            entries: [None; METHOD_COUNT],
        }
    }

    pub fn set(&mut self, method: Method, handler_id: u32) {
        self.entries[method as usize] = Some(handler_id);
    }

    pub fn get(&self, method: Method) -> Option<u32> {
        self.entries[method as usize]
    }

    pub fn has_any(&self) -> bool {
        self.entries.iter().any(|e| e.is_some())
    }

    pub fn has_method(&self, method: Method) -> bool {
        self.entries[method as usize].is_some()
    }
    
    pub fn entries(&self) -> &[Option<u32>; METHOD_COUNT] {
        &self.entries
    }
}

impl Default for Handlers {
    fn default() -> Self {
        Self::new()
    }
}

pub struct Node {
    pub prefix: Vec<u8>,
    pub node_type: NodeType,
    pub handlers: Handlers,
    pub static_children: Vec<Box<Node>>,
    pub param_child: Option<Box<ParamNode>>,
    pub wildcard_child: Option<Box<Node>>,
    pub param_name: Option<String>,
    pub wildcard_name: Option<String>,
    pub priority: u32,
}

impl Default for Node {
    fn default() -> Self {
        Self::new(NodeType::Static)
    }
}

impl Clone for Node {
    fn clone(&self) -> Self {
        Self {
            prefix: self.prefix.clone(),
            node_type: self.node_type,
            handlers: self.handlers.clone(),
            static_children: self.static_children.clone(),
            param_child: self.param_child.as_ref().map(|p| {
                Box::new(ParamNode {
                    name: p.name.clone(),
                    node: p.node.clone(),
                })
            }),
            wildcard_child: self.wildcard_child.clone(),
            param_name: self.param_name.clone(),
            wildcard_name: self.wildcard_name.clone(),
            priority: self.priority,
        }
    }
}

impl Clone for ParamNode {
    fn clone(&self) -> Self {
        Self {
            name: self.name.clone(),
            node: self.node.clone(),
        }
    }
}

pub struct ParamNode {
    pub name: String,
    pub node: Node,
}

impl Node {
    pub fn new(node_type: NodeType) -> Self {
        Self {
            prefix: Vec::new(),
            node_type,
            handlers: Handlers::new(),
            static_children: Vec::new(),
            param_child: None,
            wildcard_child: None,
            param_name: None,
            wildcard_name: None,
            priority: 0,
        }
    }

    pub fn with_prefix(prefix: &[u8]) -> Self {
        Self {
            prefix: prefix.to_vec(),
            node_type: NodeType::Static,
            handlers: Handlers::new(),
            static_children: Vec::new(),
            param_child: None,
            wildcard_child: None,
            param_name: None,
            wildcard_name: None,
            priority: 0,
        }
    }

    pub fn add_handler(&mut self, method: Method, handler_id: u32) {
        self.handlers.set(method, handler_id);
    }

    pub fn find_static_child(&self, first_byte: u8) -> Option<usize> {
        self.static_children
            .iter()
            .position(|c| !c.prefix.is_empty() && c.prefix[0] == first_byte)
    }

    pub fn insert_static_child(&mut self, child: Box<Node>) {
        let first_byte = child.prefix[0];
        if let Some(idx) = self.find_static_child(first_byte) {
            let existing = &mut self.static_children[idx];
            Self::insert_recursive(existing, child);
        } else {
            self.static_children.push(child);
        }
    }

    fn insert_recursive(target: &mut Node, new_node: Box<Node>) {
        let common_len = target
            .prefix
            .iter()
            .zip(new_node.prefix.iter())
            .take_while(|(a, b)| a == b)
            .count();

        if common_len == target.prefix.len() {
            let remaining = &new_node.prefix[common_len..];
            let mut child = Node::with_prefix(remaining);
            child.handlers = new_node.handlers;
            child.node_type = new_node.node_type;
            child.static_children = new_node.static_children;
            child.param_child = new_node.param_child;
            child.wildcard_child = new_node.wildcard_child;
            child.param_name = new_node.param_name;
            child.wildcard_name = new_node.wildcard_name;
            child.priority = new_node.priority;
            target.static_children.push(Box::new(child));
        } else if common_len == new_node.prefix.len() {
            let remaining = target.prefix[common_len..].to_vec();
            target.prefix.truncate(common_len);

            let mut split_child = Node::with_prefix(&remaining);
            split_child.handlers = std::mem::take(&mut target.handlers);
            split_child.static_children = std::mem::take(&mut target.static_children);
            split_child.param_child = std::mem::take(&mut target.param_child);
            split_child.wildcard_child = std::mem::take(&mut target.wildcard_child);
            split_child.param_name = std::mem::take(&mut target.param_name);
            split_child.wildcard_name = std::mem::take(&mut target.wildcard_name);

            target.handlers = new_node.handlers;
            target.param_name = new_node.param_name;
            target.wildcard_name = new_node.wildcard_name;
            target.static_children.push(Box::new(split_child));
        } else {
            let remaining_old = target.prefix[common_len..].to_vec();
            let remaining_new = new_node.prefix[common_len..].to_vec();

            target.prefix.truncate(common_len);

            let mut split_old = Node::with_prefix(&remaining_old);
            split_old.handlers = std::mem::take(&mut target.handlers);
            split_old.static_children = std::mem::take(&mut target.static_children);
            split_old.param_child = std::mem::take(&mut target.param_child);
            split_old.wildcard_child = std::mem::take(&mut target.wildcard_child);
            split_old.param_name = std::mem::take(&mut target.param_name);
            split_old.wildcard_name = std::mem::take(&mut target.wildcard_name);

            let mut split_new = Node::with_prefix(&remaining_new);
            split_new.handlers = new_node.handlers;
            split_new.param_name = new_node.param_name;
            split_new.wildcard_name = new_node.wildcard_name;

            target.handlers = Handlers::new();
            target.param_name = None;
            target.wildcard_name = None;
            target.static_children.push(Box::new(split_old));
            target.static_children.push(Box::new(split_new));
        }
    }

    pub fn match_path<'a>(
        &self,
        path: &'a [u8],
        path_str: &'a str,
        offset: u32,
        params: &mut Params,
    ) -> Option<(u32, Params)> {
        if path.len() < self.prefix.len() {
            return None;
        }

        if !path[..self.prefix.len()].eq_ignore_ascii_case(&self.prefix) {
            return None;
        }

        let remaining = &path[self.prefix.len()..];
        let current_offset = offset + self.prefix.len() as u32;

        if remaining.is_empty() {
            return self.handlers.entries().iter().find_map(|h| {
                h.map(|id| (id, params.clone()))
            });
        }

        for child in &self.static_children {
            if let Some(result) = child.match_path(remaining, path_str, current_offset, &mut params.clone()) {
                return Some(result);
            }
        }

        if let Some(ref param_node) = self.param_child {
            let seg_end = remaining.iter().position(|&b| b == b'/').unwrap_or(remaining.len());
            let seg = &remaining[..seg_end];
            if !seg.is_empty() {
                let mut new_params = params.clone();
                new_params.push(
                    &param_node.name,
                    current_offset,
                    seg_end as u32,
                );
                let next_remaining = &remaining[seg_end..];
                let next_offset = current_offset + seg_end as u32;
                if next_remaining.is_empty() {
                    if let Some(handler_id) = param_node.node.handlers.entries().iter().find_map(|&h| h) {
                        return Some((handler_id, new_params));
                    }
                } else {
                    if let Some(result) = param_node.node.match_path(next_remaining, path_str, next_offset, &mut new_params) {
                        return Some(result);
                    }
                }
            }
        }

        if let Some(ref wildcard) = self.wildcard_child {
            let mut new_params = params.clone();
            let name = wildcard.wildcard_name.as_deref().unwrap_or("path");
            new_params.push(name, current_offset, remaining.len() as u32);
            if let Some(handler_id) = wildcard.handlers.entries().iter().find_map(|&h| h) {
                return Some((handler_id, new_params));
            }
        }

        None
    }

    pub fn find_handler(&self, method: Method) -> Option<u32> {
        self.handlers.get(method)
    }
}

impl fmt::Debug for Node {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Node")
            .field("prefix", &String::from_utf8_lossy(&self.prefix))
            .field("type", &self.node_type)
            .field("children", &self.static_children.len())
            .finish()
    }
}
