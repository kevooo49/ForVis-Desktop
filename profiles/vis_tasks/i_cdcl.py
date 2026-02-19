import sys
import random
from pprint import pprint
from dataclasses import dataclass
from typing import List, Set, Tuple, Optional, Iterator, Dict

options = {
    "nodes": {
        "color": {"border": 'rgb(0,0,0)', "background": 'rgb(30,144,255)'},
        "font": {
            "color": "rgb(0,0,0)"
        }
    },
    "edges": {
        "enabled": True,
        "arrows": {
            "to": {
                "enabled": True,
                "scaleFactor": 1,
                "type": "arrow"
            }
        }
    },
    "physics": {
        "enabled": True,
        "barnesHut": {
            "avoidOverlap": 1,
            "centralGravity": 3.5
        },
        "maxVelocity": 1,
        "minVelocity": 1
    },
    "layout": {
        "hierarchical": {
            "direction": "UD",
            "nodeSpacing": 150
        }
    }
}

import math

class SemanticProfiler:
    def __init__(self, variables):
        self.conflict_counts = {v: 0 for v in variables}
        self.backjump_impact = {v: 0 for v in variables}
        self.propagation_power = {v: 0 for v in variables}
        self.total_decisions = {v: 0 for v in variables}

    def record_conflict(self, conflict_clause):
        """Wywoływane wewnątrz analyze_conflict"""
        for literal in conflict_clause:
            var = abs(literal)
            self.conflict_counts[var] += 1

    def record_backjump(self, decision_var, levels_jumped):
        """Wywoływane po znalezieniu konfliktu i obliczeniu poziomu powrotu"""
        if decision_var:
            self.backjump_impact[decision_var] += levels_jumped

    def record_propagation(self, decision_var, num_implications):
        """Wywoływane po Unit Propagation wywołanym przez decision_var"""
        if decision_var:
            self.propagation_power[decision_var] += num_implications
            self.total_decisions[decision_var] += 1

    def get_semantic_scores(self):
        """Agreguje dane i zwraca znormalizowany wynik [0, 1]"""
        scores = {}
        for v in self.conflict_counts.keys():
            conf = math.log1p(self.conflict_counts[v])
            bj = math.log1p(self.backjump_impact[v])
            
            avg_prop = self.propagation_power[v] / max(1, self.total_decisions[v])
            
            # Formuła końcowa (można dostosować wagi)
            raw_score = (conf * 0.5) + (bj * 0.3) + (avg_prop * 0.2)
            scores[v] = raw_score
        if not scores: return {}
        max_val = max(scores.values()) or 1.0
        return {v: round(s / max_val, 3) for v, s in scores.items()}

class GraphNode:
    def __init__(self, id, literal=None, decision_level=None, type="decision", parent_id=None, color='rgb(0,0,0)'):
        self.id = id 
        self.literal = literal 
        self.decision_level = decision_level
        self.type = type 
        self.parent_id = parent_id 
        self.children_ids = [] 
        self.status = "active" 
        self.assignments = {}
        self.current_clauses = []
        self.propagated = []
        self.color = color
        
    def add_propagated(self, propagated_new):
        self.propagated.extend(propagated_new)


class GraphEdge:
    def __init__(self, id, source_id, target_id, type="decision", color='rgb(135,206,250)'):
        self.id = id
        self.source = source_id
        self.target = target_id
        self.type = type # decision_true, decision_false, implication, conflict, satisfied
        self.color = color
def generate_unique_id(elements):
  if len(elements) == 0:
    return 0
   
  return elements[-1].id + 1

@dataclass(frozen=True)
class Literal:
    variable: int
    negation: bool
    def neg(self) -> 'Literal':
        """
        Return the negation of this literal.
        """
        return Literal(self.variable, not self.negation)


@dataclass
class Clause:
    literals: List[Literal]
    def __iter__(self) -> Iterator[Literal]:
        return iter(self.literals)

    def __len__(self):
        return len(self.literals)
    
@dataclass
class Formula:
    clauses: List[Clause]
    __variables: Set[int]

    def __init__(self, clauses: List[Clause]):
        self.clauses = []
        self.__variables = set()
        for clause in clauses:
            self.clauses.append(Clause(list(set(clause))))
            for lit in clause:
                var = lit.variable
                self.__variables.add(var)

    def variables(self) -> Set[int]:
        return self.__variables

    def __iter__(self) -> Iterator[Clause]:
        return iter(self.clauses)

    def __len__(self):
        return len(self.clauses)

@dataclass
class Assignment:
    value: bool
    antecedent: Optional[Clause]
    dl: int 
    id: int
class Assignments(dict):
    def __init__(self):
        super().__init__()

        self.dl = 0
        self.id = 0

    def value(self, literal: Literal) -> bool:
        if literal.negation:
            return not self[literal.variable].value
        else:
            return self[literal.variable].value

    def assign(self, variable: int, value: bool, antecedent: Optional[Clause]):
        self.id += 1
        self[variable] = Assignment(value, antecedent, self.dl, self.id)

    def unassign(self, variable: int):
        self.pop(variable)

    def satisfy(self, formula: Formula) -> bool:
        for clause in formula:
            if True not in [self.value(lit) for lit in clause]:
                return False
        return True

@dataclass
class VSIDSMap:
    def __init__(self, formula: Formula, decay_factor=0.95):
        # Inicjalizujemy liczniki dla każdej zmiennej na 0
        self.scores = {var: 0.0 for var in formula.variables()}
        self.phases = {var: False for var in formula.variables()}
        self.decay_factor = decay_factor
        self.increment = 1.0
    def update_phase(self, var, value):
        """Wywołuj to w solverze przy KAŻDYM przypisaniu (decyzja/UP)"""
        self.phases[var] = value
    def update_score(self, var):
        """Zwiększamy wynik zmiennej, która brała udział w konflikcie."""
        self.scores[var] += self.increment

    def decay_scores(self):
        """Mechanizm zapominania - zwiększamy przyszły przyrost (efekt relatywny)."""
        self.increment /= self.decay_factor

    def pick_variable(self, unassigned_vars):
        """Wybiera zmienną o najwyższym wyniku spośród nieprzypisanych."""
        if not unassigned_vars:
            return None, None
        var = max(unassigned_vars, key=lambda v: self.scores[v])
        return var, self.phases[var]

    def rescale_scores(self):
        """Zapobieganie przepełnieniu (overflow) liczb zmiennoprzecinkowych."""
        if self.increment > 1e100:
            for var in self.scores:
                self.scores[var] /= 1e100
            self.increment /= 1e100
@dataclass
class DLISMap:
    clauses: List[Clause]
    def __init__(self, formula: Formula):
        clauses = []
        for c in formula.clauses:
            clauses.append(c)
        self.clauses = clauses

    def pick_variable(self, unassigned_vars, current_assignment: Assignments):
        """
        Wybiera zmienną i wartość (True/False), która pojawia się 
        najczęściej w niespełnionych klauzulach.
        """
        unresolved_clauses = [
            c for c in self.clauses 
            if not self._is_clause_satisfied(c, current_assignment)
        ]

        if not unresolved_clauses:

            return unassigned_vars[0], True

        literal_counts = {}
        for var in unassigned_vars:
            literal_counts[var] = 0  
            literal_counts[-var] = 0 

        for clause in unresolved_clauses:
            for literal in clause.literals:
                var = literal.variable
                if literal.negation:
                    var *= (-1)
                if var in unassigned_vars:
                    literal_counts[var] += 1

        best_literal = max(literal_counts, key=literal_counts.get)
        
        # Zwracamy numer zmiennej i sugerowaną wartość logiczną
        variable = abs(best_literal)
        value = True if best_literal > 0 else False
        
        return variable, value

    def _is_clause_satisfied(self, clause: Clause, assignment: Assignments):
        for literal in clause.literals:
            var = literal.variable
            if var in assignment:
                if (literal.negation == False and assignment[var].value is True) or \
                   (literal.negation and assignment[var].value is False):
                    return True
        return False
class CDCLSolver:
    def __init__(self, formula: Formula, heuristic_type = 1, semantic_profile=False):
        self.heuristic_type = heuristic_type # 1 - VSIDS, 2 - DLIS
        self.formula = formula
        self.nodes = []
        self.edges = []
        self.vsids = VSIDSMap(self.formula)
        self.dlis = DLISMap(self.formula)
        self.assignments = Assignments()
        self.semantic_profile = semantic_profile
        self.profiler = None
    def add_learnt_clause(self, formula: Formula, clause: Clause):
        formula.clauses.append(clause)
    def all_variables_assigned(self, formula: Formula, assignments: Assignments) -> bool:
        return len(formula.variables()) == len(assignments)
    def pick_branching_variable(self, formula: Formula, assignments: Assignments) -> Tuple[int, bool]:

        unassigned_vars = self.get_unassigned_variables()
        
        if self.heuristic_type == 1:
            var, val = self.vsids.pick_variable(unassigned_vars=unassigned_vars)
        elif self.heuristic_type == 2:
            var, val = self.dlis.pick_variable(unassigned_vars, self.assignments)
        else:
            var = random.choice(unassigned_vars)
            val = random.choice([True, False])
        if var is None:
            var = random.choice(unassigned_vars)
        if val is None:
            val = random.choice([True, False])
        
        return (var, val)
    def backtrack(self, assignments: Assignments, b: int):
        to_remove = []
        for var, assignment in assignments.items():
            if assignment.dl > b:
                to_remove.append(var)
                
        for var in to_remove:
            assignments.pop(var)
    def get_unassigned_variables(self):
        unassigned_vars = [var for var in self.formula.variables() if var not in self.assignments]
        return unassigned_vars
    def clause_status(self, clause: Clause, assignments: Assignments) -> str:
        values = []
        for literal in clause:
            if literal.variable not in assignments:
                values.append(None)
            else:
                values.append(assignments.value(literal))

        if True in values:
            return 'satisfied'
        elif values.count(False) == len(values):
            return 'unsatisfied'
        elif values.count(False) == len(values) - 1:
            return 'unit'
        else:
            return 'unresolved'


    def unit_propagation(self, formula: Formula, assignments: Assignments) -> Tuple[str, Optional[Clause], Optional[list]]:
        finish = False
        propagated = []
        while not finish:
            finish = True
            for clause in formula:
                status = self.clause_status(clause, assignments)
                if status == 'unresolved' or status == 'satisfied':
                    continue
                elif status == 'unit':
                    literal = next(literal for literal in clause if literal.variable not in assignments)
                    var = literal.variable
                    val = not literal.negation
                    propagated.append((var, val))
                    assignments.assign(var, val, antecedent=clause)
                    if self.heuristic_type == 1:
                        self.vsids.update_phase(var, val)
                    finish = False
                else:
                    return ('conflict', clause, propagated)

        return ('unresolved', None, propagated)
    def resolve(self, a: Clause, b: Clause, x: int) -> Clause:
        result = set(a.literals + b.literals) - {Literal(x, True), Literal(x, False)}
        result = list(result)
        return Clause(result)


    def conflict_analysis(self, clause: Clause, assignments: Assignments) -> Tuple[int, Clause]:
        if assignments.dl == 0:
            return (-1, None)
    
        literals = [literal for literal in clause if assignments[literal.variable].dl == assignments.dl]
        while len(literals) != 1:
            literals = filter(lambda lit: assignments[lit.variable].antecedent != None, literals)

            literal = next(literals)
            antecedent = assignments[literal.variable].antecedent
            clause = self.resolve(clause, antecedent, literal.variable)

            literals = [literal for literal in clause if assignments[literal.variable].dl == assignments.dl]

        decision_levels = sorted(set(assignments[literal.variable].dl for literal in clause))
        if len(decision_levels) <= 1:
            return 0, clause
        else:
            return decision_levels[-2], clause
    def last_node(self, b: int) -> GraphNode:
        for node in self.nodes:
            if node.decision_level == b:
                return node
        return None
    def cdcl_solve(self, formula: Formula) -> Optional[Assignments]:
        if self.semantic_profile:
            self.profiler = SemanticProfiler(list(self.formula.variables()))
        node_0 = GraphNode(id=0, type="start", decision_level=0, color="rgb(145, 1, 114)")
        self.nodes.append(node_0)
        current_node = node_0
        
        reason, clause, prop = self.unit_propagation(formula, self.assignments)
        current_node.add_propagated(prop)
        if reason == 'conflict':
            return None

        while not self.all_variables_assigned(formula, self.assignments):
            var, val = self.pick_branching_variable(formula, self.assignments)
            if self.semantic_profile:
                self.profiler.total_decisions[var] += 1
                current_decision_var = var

            new_node_id = generate_unique_id(self.nodes)
            new_node = GraphNode(id=new_node_id, literal=var, 
                                decision_level=self.assignments.dl+1, type="decision", parent_id=current_node.id, color='rgb(43, 77, 181)')
            new_node.add_propagated([(var, val)])
            current_node.children_ids.append(new_node_id)
            edge = GraphEdge(id=generate_unique_id(self.edges), source_id=current_node.id, target_id=new_node_id, type="decision", color='rgb(81, 15, 140)')
            current_node = new_node
            self.nodes.append(new_node)
            self.edges.append(edge)

            self.assignments.dl += 1
            self.assignments.assign(var, val, antecedent=None)
            if self.heuristic_type == 1:
                self.vsids.update_phase(var, val)
            while True:
                reason, clause, prop = self.unit_propagation(formula, self.assignments)
                if reason != 'conflict':
                    current_node.add_propagated(prop)
                    if self.semantic_profile:
                        self.profiler.record_propagation(current_decision_var, len(prop))
                    break
                conflict_node = GraphNode(id=generate_unique_id(self.nodes), type="conflict",
                                        decision_level=self.assignments.dl+1, parent_id=current_node.id, color="rgb(120, 29, 8)")
                current_node.children_ids.append(-1)
                conflict_edge = GraphEdge(id=generate_unique_id(self.edges), 
                                        source_id=current_node.id, target_id=conflict_node.id, type="conflict",color="rgb(191, 35, 0)"
                                        )
                
                conflict_node.status = "conflict"
                self.nodes.append(conflict_node)
                self.edges.append(conflict_edge)
                
                b, learnt_clause = self.conflict_analysis(clause, self.assignments)
                if self.semantic_profile:
                    lits = [abs(lit.variable) for lit in learnt_clause.literals]
                    self.profiler.record_conflict(lits)
                    
                    jump_dist = self.assignments.dl - b
                    self.profiler.record_backjump(current_decision_var, jump_dist)
                if b < 0:
                    return None
                if self.heuristic_type == 1:
                    for lit in learnt_clause.literals:
                        var = abs(lit.variable)
                        self.vsids.update_score(var)
                    self.vsids.decay_scores()
                
                self.add_learnt_clause(formula, learnt_clause)
                self.backtrack(self.assignments, b)
                self.assignments.dl = b
                current_node = self.last_node(b)
        satisfied_node_id = generate_unique_id(self.nodes)
        satisfied_node = GraphNode(id=satisfied_node_id, type="satisfied",decision_level=self.assignments.dl+1, parent_id=current_node.id, color="rgb(44, 153, 0)")
        current_node.children_ids.append(satisfied_node_id)
        satisfied_edge = GraphEdge(id=generate_unique_id(self.edges), source_id=current_node.id, target_id=satisfied_node_id, type="satisfied", color="rgb(0, 163, 44)")
        self.nodes.append(satisfied_node)
        self.edges.append(satisfied_edge)
        current_node.status = "satisfied"
        return self.assignments, self.nodes, self.edges


def made_tree(nodes: List[GraphNode], edges: List[GraphEdge]):
    nodes_json = {}
    edges_json = {}
    shapes = {"decision": "ellipse", "conflict": "diamond", "satisfied": "box", 'start': "circle"}
    for n in nodes:
        
        label = "" 
        if n.type == "decision":
            if len(n.propagated) > 0:
                for prop in n.propagated:
                    label += f'x{prop[0]}: {prop[1]} '
            else:
                label = f'x{n.literal}'
        elif n.type == "conflict":
            label = "Conflict"
        elif n.type == "satisfied":
            label = "SAT"
        elif n.type == "start":
            label = "start"
        else:
            label = "not of"
        nodes_json[n.id] = {"id": n.id, "label": label, 
                            "level": n.decision_level, "color": {"background": n.color},
                            "shape": shapes[n.type]}
    for e in edges:
        edges_json[e.id] = {"from": e.source, "to":e.target, "color": e.color}
    return nodes_json, edges_json

# cdcl - Conflict-driven clause learning
# VSIDS -  Variable State Independent Decaying Sum
# DLIS - Dynamic Largest Individual Sum