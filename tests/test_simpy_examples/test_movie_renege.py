from dataclasses import dataclass

import simpy as SIM
import upstage_des.api as UP
import pytest

from upstage_des.events import is_event_complete, make_random_timeout


class Theater(UP.Actor):
    counter: SIM.Resource = UP.ResourceState(default=SIM.Resource).create()
    movies: list[str]
    available: dict[str, int]
    sold_out: dict[str, SIM.Event]
    when_sold_out: str = UP.State(default="", recording=True).create()
    num_renegers: dict[str, int]
    sellout: int

    def check_sellout(self, movie: str) -> None:
        if self.available[movie] < self.sellout:
            # Trigger the "sold out" event for the movie
            self.sold_out[movie].succeed()
            self.when_sold_out = movie
            self.available[movie] = 0


@dataclass
class MGKnow(UP.Knowledge):
    theater: Theater
    movie: str
    tickets: int


class Moviegoer(UP.Actor):
    """A buyer of tickets for a movie in a theater."""
    knowledge: MGKnow = UP.State(default_factory=MGKnow.make_blank).create()


class ArriveAndWait(UP.Task):
    def task(self, *, actor: Moviegoer) -> UP.TASK_GEN:
        theater = actor.knowledge.theater
        movie = actor.knowledge.movie
        n_tickets = actor.knowledge.tickets

        # As we walk up to the counter, look at the "sign"
        if theater.available[movie] == 0:
            actor.write_to_log(f"'{movie}' is sold out when we arrived")
            self.set_actor_task_queue(actor, ["GoHome"])
            return

        req = theater.counter.request()
        yield req | theater.sold_out[movie]
        # If the movie sold out, go home.
        if not is_event_complete(req):
            assert is_event_complete(theater.sold_out[movie])
            theater.num_renegers[movie] += 1
            actor.write_to_log(f"'{movie}' is sold out")
            self.set_actor_task_queue(actor, ["GoHome"])
            req.cancel()
            return

        # If there aren't enough tickets, go home
        if theater.available[movie] < n_tickets:
            actor.write_to_log(f"Arguing because we can't see {movie}")
            yield UP.Timeout(0.5)
            self.set_actor_task_queue(actor, ["GoHome"])
            theater.counter.release(req)
            return

        theater.available[movie] -= n_tickets
        # For a more complete UPSTAGE example, the theater would be told
        # the number of tickets bought, and this processing would not
        # happen here. That way, if a sellout needed to cause further action
        # it could be implemented in the right spot.
        theater.check_sellout(movie)
        theater.counter.release(req)
        self.set_actor_task_queue(actor, ["WatchMovie"])


class WatchMovie(UP.Task):
    def task(self, *, actor: Moviegoer) -> UP.TASK_GEN:
        yield make_random_timeout(1.5, 2.2)
        self.set_actor_task_queue(actor, ["GoHome"])


class GoHome(UP.TerminalTask): ...


moviegoer_taskfactory = UP.TaskNetworkFactory(
    name="GoToMovies",
    task_classes={
        ArriveAndWait: UP.TaskLinks(default=None, allowed=[WatchMovie, GoHome]),
        WatchMovie: UP.TaskLinks(default=GoHome, allowed=[GoHome]),
        GoHome: UP.TaskLinks(default=None,),
    }
)


class MoviegoerMaker(UP.Task):
    """We don't need a task to do this, but it's possible.
    
    It gives us quick access to the environment, etc.

    Alternatively, we could have made a function to do this and used
    `get_entities_by_class()`, `get_env()`, `get_stage()`, etc. functions
    to also get to the scope of the sim.
    """
    def task(self, *, actor: Theater) -> UP.TASK_GEN:
        n_viewer = 1
        while True:
            rng = self.stage.random
            t_to_next = rng.expovariate(1 / 0.15)
            movie = rng.choice(actor.movies)
            num_tickets = rng.randint(1, 6)
            print(f"{self.env.now + t_to_next:.2f}", movie, num_tickets)
            yield UP.Timeout(t_to_next)
            goer = Moviegoer(
                name = f"Person {n_viewer}",
                knowledge=MGKnow(
                    actor,
                    movie,
                    num_tickets,
                ),
            )
            net = moviegoer_taskfactory.make_network()
            goer.add_task_network(net)
            goer.start_network_loop(net.name, ArriveAndWait)
            n_viewer += 1


def test_movie_renege() -> None:
    TICKETS = 50  # Number of tickets per movie
    SELLOUT_THRESHOLD = 2  # Fewer tickets than this is a sellout
    SIM_TIME = 120  # Simulate until
    movies = ['Python Unchained', 'Kill Process', 'License To GIL']

    with UP.EnvironmentContext(random_seed=1209) as env:
        cineplex = Theater(
            name="Fun Time Movie Grill Studio",
            movies = movies,
            available = {k: TICKETS for k in movies},
            sold_out = {k: UP.Event() for k in movies},
            when_sold_out="",
            num_renegers=dict.fromkeys(movies, 0),
            sellout=SELLOUT_THRESHOLD,
        )
        cineplex.update_resource("counter", capacity=1)

        mgm = MoviegoerMaker()
        mgm.run(actor=cineplex)

        env.run(until=SIM_TIME)

        # grab all the moviegoers and make sure the data make sense.
        # mgoers: list[Moviegoer] = UP.get_entities_by_class("Moviegoer")

        # Tuned the sim to make some people leave the line.
        assert any(v > 0 for v in cineplex.num_renegers.values())


test_movie_renege()
