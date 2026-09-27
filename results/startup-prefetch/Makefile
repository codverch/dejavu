STAGES = trace-dr trace-native convert summarize analyze build sim-baseline sim-ideal fetch figures

all:
	./run.sh all

$(STAGES):
	./run.sh $@

.PHONY: all $(STAGES)
