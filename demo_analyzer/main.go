// Thin, non-interactive JSON adapter around the pinned cs2-analyser-tool API.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/taua-almeida/cs2-analyser-tool/analysis"
)

func main() {
	demo := flag.String("demo", "", "path to a CS2 .dem file")
	timeout := flag.Duration("timeout", 14*time.Minute, "parse timeout")
	flag.Parse()
	if *demo == "" {
		fmt.Fprintln(os.Stderr, "--demo is required")
		os.Exit(2)
	}
	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()
	result, err := analysis.AnalyseFile(ctx, *demo)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(result); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
